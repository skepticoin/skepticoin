from setuptools import setup, find_packages

setup(
    name="scepticoin",
    description="The Coin for Non-Believers",
    author="Sashimi Houdini",

    install_requires=[
        "scrypt>=0.8.17",
        "ecdsa>=0.16.1",
        "immutables>=0.15",
    ],

    packages=find_packages(),

    setup_requires=["setuptools_scm"],
    use_scm_version={
        "write_to": "scepticoin/scmversion.py",
        "write_to_template": "__version__ = '{version}'\n",
    },

    include_package_data=True,

    entry_points={
        'console_scripts': [
            'scepticoin-mine=scepticoin.scripts.mine:main',
        ],
    },

    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',

        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',

        # 'License :: OSI Approved :: Python Software Foundation License',

        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',

        'Programming Language :: Python',
    ],
)
