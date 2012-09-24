from setuptools import setup, find_packages


setup(name='chromescript',
      version="0.1",
      author="Mike Spindel",
      author_email="mike@spindel.is",
      license="MIT",
      keywords="google chrome applescript",
      url="http://github.com/deactivated/chromescript",
      description='Control Google Chrome via Applescript.',
      install_requires=["python-snss"],
      packages=find_packages(),
      zip_safe=False,
      classifiers=[
          "Development Status :: 4 - Beta",
          "License :: OSI Approved :: MIT License",
          "Intended Audience :: Developers",
          "Natural Language :: English",
          "Programming Language :: Python"])
