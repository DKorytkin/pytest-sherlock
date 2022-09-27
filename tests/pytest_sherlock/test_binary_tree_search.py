import pytest

from pytest_sherlock.binary_tree_search import Node, draw_tree, length, make_tee


def test_create_node_with_default_params():
    tests_range = (0, 3)
    node = Node(tests_range)
    assert node.items == tests_range
    assert node.left is None and node.right is None


def test_modify_node_prams():
    tests_range = (0, 3)
    node = Node(tests_range, Node((0, 1)), Node((1, 3)))
    assert node.items == tests_range
    assert isinstance(node.left, Node) and isinstance(node.right, Node)


def test_make_tree_with_even_data():
    """
    Example of tree:
              ________(0, 4)_________
             /                       \
        __(0, 2)___             __(2, 4)___
       /           \           /           \
    (0, 1)      (1, 2)      (2, 3)      (3, 4)
    """
    tests_range = (0, 4)
    root = make_tee(tests_range)
    assert isinstance(root, Node)
    assert root.items == tests_range

    assert isinstance(root.left, Node)
    assert root.left.items == (0, 2)

    assert root.left.left.items == (0, 1)
    assert root.left.left.left is None
    assert root.left.left.right is None
    assert isinstance(root.left.right, Node)
    assert root.left.right.items == (1, 2)
    assert root.left.right.left is None
    assert root.left.right.right is None

    assert isinstance(root.right, Node)
    assert root.right.items == (2, 4)

    assert isinstance(root.right.right, Node)
    assert root.right.left.items == (2, 3)
    assert root.right.left.left is None
    assert root.right.left.right is None
    assert isinstance(root.right.right, Node)
    assert root.right.right.items == (3, 4)
    assert root.right.right.left is None
    assert root.right.right.right is None


def test_make_tree_with_not_even_data():
    """
    Example of tree:
              ________(0, 5)_________
             /                       \
        __(0, 2)___             __(2, 5)_________
       /           \           /                 \
    (0, 1)      (1, 2)      (2, 3)          __(3, 5)___
                                           /           \
                                        (3, 4)      (4, 5)
    """
    tests_range = (0, 5)
    root = make_tee(tests_range)
    assert isinstance(root, Node)
    assert root.items == tests_range

    assert isinstance(root.left, Node)
    assert root.left.items == (0, 2)

    assert root.left.left.items == (0, 1)
    assert root.left.left.left is None
    assert root.left.left.right is None
    assert isinstance(root.left.right, Node)
    assert root.left.right.items == (1, 2)
    assert root.left.right.left is None
    assert root.left.right.right is None

    assert isinstance(root.right, Node)
    assert root.right.items == (2, 5)

    assert isinstance(root.right.right, Node)
    assert root.right.left.items == (2, 3)
    assert root.right.left.left is None
    assert root.right.left.right is None
    assert isinstance(root.right.right, Node)
    assert root.right.right.items == (3, 5)
    assert root.right.right.left.items == (3, 4)
    assert root.right.right.right.items == (4, 5)


@pytest.mark.parametrize(
    "data",
    (
        pytest.param(tuple(), id="empty"),
        pytest.param((1, 4, 7), id="wrong_amount_of_indices"),
        pytest.param((-1, 3), id="invalid_start_index"),
        pytest.param((3, 1), id="invalid_end_index"),
        pytest.param((0, "2"), id="invalid_end_type"),
    ),
)
def test_make_tree_with_invalid_data(data):
    with pytest.raises(RuntimeError):
        make_tee(data)


@pytest.mark.parametrize(
    "data, func, exp_result",
    (
        pytest.param((0, 4), max, 3, id="max_of_even"),
        pytest.param((0, 4), min, 2, id="min_of_even"),
        pytest.param((0, 5), max, 4, id="max_of_not_even"),
        pytest.param((0, 5), min, 2, id="min_of_not_even"),
    ),
)
def test_count_length(data, func, exp_result):
    """
    Example of tree:
              ________(0, 4)_________
             /                       \
        __(0, 2)___             __(2, 4)___
       /           \           /           \
    (0, 1)      (1, 2)      (2, 3)      (3, 4)

              ________(0, 5)_________
             /                       \
        __(0, 2)___             __(2, 5)_________
       /           \           /                 \
    (0, 1)      (1, 2)      (2, 3)          __(3, 5)___
                                           /           \
                                        (3, 4)      (4, 5)

    """
    assert length(make_tee(data), func) == exp_result


def test_draw_tree(capsys):
    exp_result = (
        "          ________(0, 5)_________                     \n"
        "         /                       \\                    \n"
        "    __(0, 2)___             __(2, 5)_________         \n"
        "   /           \\           /                 \\        \n"
        "(0, 1)      (1, 2)      (2, 3)          __(3, 5)___   \n"
        "                                       /           \\  \n"
        "                                    (3, 4)      (4, 5)\n"
    )
    draw_tree(make_tee((0, 5)))
    assert capsys.readouterr().out == exp_result
