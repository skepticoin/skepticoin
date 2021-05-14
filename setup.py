from setuptools import setup, find_packages

setup(
    name="skepticoin",
    description="The Coin for Non-Believers",
    long_description=open("README.md", 'r').read(),
    long_description_content_type='text/markdown',

    author="Sashimi Houdini",
    url="https://github.com/skepticoin/skepticoin/",

    install_requires=[
        "scrypt>=0.8.17",
        "ecdsa>=0.16.1",
        "immutables>=0.15",
        "ptpython",
    ],

    packages=find_packages(),

    setup_requires=["setuptools_scm"],
    use_scm_version={
        "write_to": "skepticoin/scmversion.py",
        "write_to_template": "__version__ = '{version}'\n",
    },

    include_package_data=True,

    entry_points={
        'console_scripts': [
            'skepticoin-version=skepticoin.scripts.version:main',
            'skepticoin-mine=skepticoin.scripts.mine:main',
            'skepticoin-receive=skepticoin.scripts.receive:main',
            'skepticoin-send=skepticoin.scripts.send:main',
            'skepticoin-repl=skepticoin.scripts.repl:main',
            'skepticoin-run=skepticoin.scripts.run:main',
            'skepticoin-balance=skepticoin.scripts.balance:main',
        ],
    },

    license="BSD-3-Clause",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',

        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',

        'License :: OSI Approved :: BSD License',

        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',

        'Programming Language :: Python',
    ],
)
