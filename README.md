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
pytest tests/exmaple/test_c_delete.py tests/exmaple/test_b_modify.py tests/exmaple/test_all_read.py --flaky-test="test_read_params" -vv
```
Plugin didn't run all tests, it try to find some possible guilty test and will run first
```bash
======================================================================================== test session starts ========================================================================================
collected 10 items                                                                                                                                                                                  
Try to find coupled tests

Step #1:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [100%]
tests/exmaple/test_c_delete.py::test_delete_random_param PASSED                                                                                                                               [200%]
tests/exmaple/test_c_delete.py::test_deleted_passed PASSED                                                                                                                                    [300%]
tests/exmaple/test_c_delete.py::test_do_not_delete PASSED                                                                                                                                     [400%]
tests/exmaple/test_all_read.py::test_read_params COUPLED                                                                                                                                      [500%]
Step #2:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [500%]
tests/exmaple/test_c_delete.py::test_delete_random_param PASSED                                                                                                                               [500%]
tests/exmaple/test_all_read.py::test_read_params COUPLED                                                                                                                                      [500%]
Step #3:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [500%]
tests/exmaple/test_all_read.py::test_read_params COUPLED 
```

### TODO
I have a couple ideas, how to improve finder coupled tests:
- use **AST** for detect common peace of code *(variables, functions, etc...)*
- **Also need to add tests for it =)**