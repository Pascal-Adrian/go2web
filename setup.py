from setuptools import setup

setup(
    name="go2web",
    version="0.1",
    py_modules=["main"],
    install_requires=[
        "beautifulsoup4",
    ],
    entry_points={
        'console_scripts': [
            'go2web=main:main',
        ],
    },
)