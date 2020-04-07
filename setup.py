from setuptools import setup, find_packages


with open("README.md", "r") as f:
    long_description = f.read()


setup(
    name="pytest-sherlock",
    version="0.1.5",
    author="Denis Korytkin",
    author_email="dkorytkin@gmail.com",
    description="pytest plugin help to find coupled tests",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DKorytkin/pytest-sherlock",
    keywords=["py.test", "pytest", "flaky", "coupled", "tests"],
    py_modules=[
        "pytest_sherlock.binary_tree_search",
        "pytest_sherlock.plugin",
        "pytest_sherlock.sherlock",
    ],
    packages=find_packages(exclude=["tests*"]),
    install_requires=["setuptools>=28.8.0", "pytest>=3.5.1"],
    entry_points={"pytest11": ["sherlock = pytest_sherlock.plugin"]},
    license="MIT license",
    python_requires=">=2.7",
    classifiers=[
        "Framework :: Pytest",
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Topic :: Utilities",
    ],
)
