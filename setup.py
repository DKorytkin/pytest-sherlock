from setuptools import setup, find_packages


def long_description():
    with open("README.md", "r") as f:
        return f.read()


setup(
    name="pytest-sherlock",
    version="0.0.1",
    author="Denis Korytkin",
    author_email="dkorytkin@gmail.com",
    description="pytest plugin help to find coupled tests",
    long_description=long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/DKorytkin/pytest-sherlock",
    keywords=["py.test", "pytest", "flaky", "coupled", "tests"],
    py_modules=["pytest_sherlock.plugin"],
    packages=find_packages(),
    install_requires=["setuptools>=28.8.0", "pytest>=3.1.2"],
    entry_points={"pytest11": ["name_of_plugin = pytest_sherlock.plugin"]},
    license="MIT license",
    classifiers=[
        "Framework :: Pytest",
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Topic :: Utilities",
    ],
)
