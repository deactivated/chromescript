import json
import os
from os.path import dirname
from subprocess import Popen, PIPE
from collections import defaultdict

from snss import SNSSFile
from appscript import app, k

__all__ = ["ChromeProcess"]


def lsof(fmt, opts):
    p = Popen(("/usr/sbin/lsof", "-F", fmt) + tuple(opts),
              stdout=PIPE, stderr=PIPE)
    p.stderr.close()

    pid = 0
    for l in p.stdout.readlines():
        l_type, l_data = l[0], l[1:-1]
        if l_type == "p":
            pid = int(l_data)

        yield (pid, (l_type, l_data))


def chrome_paths(pid=None):
    """
    Yield a (pid, config_directory) tuple for each active Chrome process.
    """
    lsof_opts = ["-b"]
    if pid:
        lsof_opts.extend(["-p", "%d" % pid])
    else:
        lsof_opts.extend(["-c", "/Google Chrome$/"])

    reported = set()
    for pid, (l_type, l_data) in lsof("pn", lsof_opts):
        if pid in reported:
            continue

        if l_type == "n" and l_data.find('Current Session') >= 0:
            reported.add(pid)
            yield pid, dirname(dirname(l_data))


class ChromeDirectory(object):

    def __init__(self):
        self.procs = None
        self.pid_map = self.path_map = self.prof_map = None

    def cache_procs(self):
        self.procs = [ChromeProcess(pid, path) for pid, path in chrome_paths()]
        self.pid_map = {proc.pid: proc for proc in self.procs}
        self.path_map = {proc.path: proc for proc in self.procs}
        self.cache_profiles()

    def cache_profiles(self):
        "Cache a map {profile_name: set(proc)}"
        prof_map = defaultdict(set)
        for proc in self.procs:
            proc_winds = set(w.id for w in proc.windows())
            for name, prof in proc.config.profiles.iteritems():
                prof_winds = set(prof.window_tab_map().keys()) & proc_winds
                if prof_winds:
                    prof_map[name].add(proc)
        self.prof_map = prof_map

    def get_process(self, path=None, pid=None, profile=None):
        if self.procs is None:
            self.cache_procs()

        if profile:
            return next(iter(self.prof_map[profile]))
        if path:
            return self.path_map[path]
        if pid:
            return self.pid_map[pid]

    def open_url(self, url, new_tab=True, path=None, pid=None, profile=None):
        "Convenience method to open a URL in a Chrome Process."
        proc = self.get_process(path=path, pid=pid, profile=profile)
        if profile:
            wind = proc.get_window(profile=profile)
        else:
            wind = proc.first_window
        if new_tab:
            wind.open_tab(url)
        else:
            wind.url = url


class ChromeProcess(object):

    def __init__(self, pid, path):
        self.pid = pid
        self.path = path
        self.app = app(pid=pid)
        self.config = ConfigReader(path)

    def profile_window_map(self):
        "Return a map {profile_name: [window_id]}"
        profiles = {}
        proc_winds = set(w.id for w in self.windows())
        for name, prof in self.config.profiles.iteritems():
            prof_winds = proc_winds & set(prof.window_tab_map().keys())
            profiles[name] = prof_winds
        return profiles

    def get_window(self, id=None, profile=None):
        if profile:
            wind_map = self.profile_window_map()
            id = next(iter(wind_map[profile]))

        wind = self.app.windows.ID(id).get()
        return ChromeWindow(self, wind)

    def open_window(self, url=None):
        wind = ChromeWindow(self, self.handle.make(new=k.window))
        if url:
            wind.url = url
        return wind

    def windows(self):
        return [ChromeWindow(self, wind) for wind in
                self.app.windows.get()]

    @property
    def first_window(self):
        wind = self.app.windows.first.get()
        return ChromeWindow(self, wind)


class ChromeWindow(object):

    def __init__(self, proc, handle=None):
        self.proc = proc
        self.handle = handle
        self.id = self.handle.id.get()

    def open_tab(self, url=None):
        tab = ChromeTab(self, self.handle.make(new=k.tab))
        if url:
            tab.url = url
        return tab

    @property
    def active_tab(self):
        tab = self.handle.active_tab.get()
        return ChromeTab(self, tab)

    @property
    def minimized(self):
        return self.handle.minimized.get()

    @property
    def url(self):
        return self.active_tab.url

    @url.setter
    def url(self, url):
        self.active_tab.url = url


class ChromeTab(object):

    def __init__(self, wind, handle=None):
        self.wind = wind
        self.handle = handle

    @property
    def url(self):
        return self.handle.URL.get()

    @url.setter
    def url(self, value):
        self.handle.set(self.handle.URL, to=value)

    def reload(self):
        self.handle.reload()


class ConfigReader(object):

    def __init__(self, chrome_path):
        self.path = chrome_path
        self.read_profiles()

    def read_profiles(self):
        config = json.load(open(os.path.join(self.path, "Local State")))
        profiles = {
            prof["name"]: Profile(os.path.join(self.path, dir_name))
            for dir_name, prof in config["profile"]["info_cache"].iteritems()
        }
        self.profiles = profiles


class Profile(object):

    def __init__(self, path):
        self.path = path

    def session_state(self):
        snss_path = os.path.join(self.path, "Current Session")
        snss_file = SNSSFile(open(snss_path))
        return snss_file

    def window_tab_map(self):
        "Return a map {window_id: set(tab_id, ...)}"
        windows = defaultdict(set)
        for cmd in self.session_state():
            if cmd.command_id == 0:
                windows[cmd['id']].add(cmd['index'])
        return windows
