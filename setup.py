#!/usr/bin/env python
import io
import os
from setuptools import setup, find_packages


def long_description():
    """
    Build the long description from a README file located in the same directory
    as this module.
    """
    base_path = os.path.dirname(os.path.realpath(__file__))
    with io.open(os.path.join(base_path, 'README.md'), encoding='utf-8') as f:
        return f.read()


setup(
    name='django-postgres-dbdefaults',
    version='0.1.1',
    description='Maintain database defaults in django sql migrations (instead of dropping them).',
    long_description=long_description(),
    author='Peter Coles',
    author_email='peter@ringly.com',
    url='https://github.com/ringly/django-postgres-dbdefaults',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Framework :: Django',
    ],
)
