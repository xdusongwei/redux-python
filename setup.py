from setuptools import setup, find_packages

setup(
    name='redux-python',
    version='0.1.0',
    author='songwei',
    author_email='songwei@songwei.io',
    description='',
    long_description='',
    url='https://github.com/xdusongwei/redux-python',
    packages=find_packages(),
    install_requires=['websockets', 'msgpack', 'pytest', 'sortedcontainers'],
    ext_modules=[],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
    ],
)
