# pytest-sherlock

[![Build Status](https://travis-ci.com/DKorytkin/pytest-sherlock.svg?branch=master)](https://travis-ci.com/DKorytkin/pytest-sherlock)
[![Cov](https://codecov.io/gh/DKorytkin/pytest-sherlock/branch/master/graph/badge.svg)](https://codecov.io/gh/DKorytkin/pytest-sherlock/branch/master)
[![PyPI](https://img.shields.io/pypi/v/pytest-sherlock)](https://pypi.org/project/pytest-sherlock/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pytest-sherlock)](https://pypi.org/project/pytest-sherlock/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/pytest-sherlock)](https://pypi.org/project/pytest-sherlock/)

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
======================= test session starts =======================
collected 10 items                                                                                                                                                                                  
Try to find coupled tests

Step #1:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [ 20%]
tests/exmaple/test_c_delete.py::test_delete_random_param PASSED                                                                                                                               [ 40%]
tests/exmaple/test_c_delete.py::test_deleted_passed PASSED                                                                                                                                    [ 60%]
tests/exmaple/test_c_delete.py::test_do_not_delete PASSED                                                                                                                                     [ 80%]
tests/exmaple/test_all_read.py::test_read_params COUPLED                                                                                                                                      [100%]
Step #2:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [ 33%]
tests/exmaple/test_c_delete.py::test_delete_random_param PASSED                                                                                                                               [ 66%]
tests/exmaple/test_all_read.py::test_read_params COUPLED                                                                                                                                      [100%]
Step #3:
tests/exmaple/test_b_modify.py::test_modify_random_param PASSED                                                                                                                               [ 50%]
tests/exmaple/test_all_read.py::test_read_params COUPLED                                                                                                                                      [100%]

============================= COUPLED ==============================
_________________________ test_read_params _________________________

config = {'a': 1, 'b': 13, 'c': 3}, param = 'b'

    def test_read_params(config, param):
>       assert config.get(param) == 2
E       AssertionError: assert 13 == 2
E        +  where 13 = <built-in method get of dict object at 0x10edb54b0>('b')
E        +    where <built-in method get of dict object at 0x10edb54b0> = {'a': 1, 'b': 13, 'c': 3}.get

tests/exmaple/test_all_read.py:8: AssertionError
=============== 7 passed, 3 coupled in 0.07 seconds ================== 
```

### TODO
I have a couple ideas, how to improve finder coupled tests:
- use **AST** for detect common peace of code *(variables, functions, etc...)*
- **Also need to add tests for it =)**