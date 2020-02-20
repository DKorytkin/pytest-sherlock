# pytest-sherlock

[![Build Status](https://travis-ci.com/DKorytkin/pytest-sherlock.svg?branch=master)](https://travis-ci.com/DKorytkin/pytest-sherlock)
[![Cov](https://codecov.io/gh/DKorytkin/pytest-sherlock/branch/master/graph/badge.svg)](https://codecov.io/gh/DKorytkin/pytest-sherlock/branch/master)

Pytest plugin which help to find coupled tests.

Sometimes we have coupled tests which depend from ordering

For example:
- **PASSES** `tests/exmaple/test_all_read.py tests/exmaple/test_b_modify.py tests/exmaple/test_c_delete.py`
- **FAILED** `tests/exmaple/test_c_delete.py tests/exmaple/test_b_modify.py tests/exmaple/test_all_read.py`

In this case pretty simple to detect coupled tests, but if we have >=1k tests which called before it will hard


## Content:
- [install](#install)
- [how to use](#how-to-use)
- [waiting in the future](#todo)

### Install
```bash
pip install pytest-sherlock
```

### how to use:
```bash
pytest tests/exmaple/test_c_delete.py tests/exmaple/test_b_modify.py tests/exmaple/test_all_read.py --flaky-test="test_read_params" -vv -x
```
Plugin didn't run all tests, it try to find some possible guilty test and will run first
```bash
======================================================================================== test session starts ========================================================================================
collected 3 items                                                                                                                                                                                   
Try to find coupled tests:

tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [ 33%]
tests/exmaple/test_all_read.py::test_read_params FAILED                                                                                                                                       [ 66%]
tests/exmaple/test_c_delete.py::test_delete_random_param PASSED                                                                                                                               [100%]

============================================================================================= FAILURES ==============================================================================================
```
Also you can use `pytest -x` or `--exitfirst`
```bash
======================================================================================== test session starts ========================================================================================
collected 3 items                                                                                                                                                                                   
Try to find coupled tests:

tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [ 33%]
tests/exmaple/test_all_read.py::test_read_params FAILED                                                                                                                                       [ 66%]

============================================================================================= FAILURES ==============================================================================================
```

### TODO
I have a couple ideas, how to improve finder coupled tests:
- use **AST** for detect common peace of code *(variables, functions, etc...)*
- run not all tests *(binary search algorithm)*
- **Also need to add tests for it =)**