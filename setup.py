from setuptools import setup, find_packages


def long_description():
    with open("README.md", "r") as f:
        return f.read()


setup(
    name="pytest_hercule",
    version="0.0.1",
    author="Denis Korytkin",
    author_email="dkorytkin@gmail.com",
    description="pytest plugin help to find coupled tests",
    long_description=long_description(),
    url="https://github.com/DKorytkin/pytest_hercule",
    keywords=["py.test", "pytest", "flaky", "coupled", "tests"],
    py_modules=["pytest_hercule.plugin"],
    packages=find_packages(),
    install_requires=["setuptools>=40.0", "pytest >= 3.1.2"],
    entry_points={"pytest11": ["name_of_plugin = pytest_hercule.plugin"]},
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
