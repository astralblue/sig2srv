#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

requirements = [
    'ctorrepr',
]

setup_requirements = [
    'pytest-runner',
]

test_requirements = [
    'pytest',
    'pytest-asyncio',
    'pytest-timeout',
    'asynciotimemachine',
]

setup(
    name='sig2srv',
    version='0.1.1',
    description="sig2srv converts incoming signals into suitable service(8) "
                "commands.",
    long_description=readme + '\n\n' + history,
    author="Eugene M. Kim",
    author_email='astralblue@gmail.com',
    url='https://github.com/astralblue/sig2srv',
    packages=find_packages(include=['sig2srv']),
    include_package_data=True,
    install_requires=requirements,
    license="MIT license",
    zip_safe=False,
    keywords='sig2srv',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    test_suite='tests',
    tests_require=test_requirements,
    setup_requires=setup_requirements,
    entry_points={
        'console_scripts': ['sig2srv=sig2srv.cli:main'],
    }
)
