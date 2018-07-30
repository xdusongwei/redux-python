from setuptools import setup

setup(
    name='redux-python',
    version='0.1.0',
    author='songwei',
    author_email='songwei@songwei.io',
    description='',
    long_description='',
    url='https://github.com/xdusongwei/redux-python',
    packages=['redux', ],
    ext_modules=[],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
    ],
    install_requires=[
        'websockets',
    ],
)
