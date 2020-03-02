import pytest

from pytest_sherlock.binary_tree_search import Root, Node


@pytest.fixture()
def root():
    return Root()


def test_create_node_with_default_params():
    data = range(3)
    node = Node(data)
    assert node.value == data
    assert node.left is None and node.right is None


def test_modify_node_prams():
    data = range(3)
    node = Node(data)
    mid = len(data) // 2
    node.left = Node(data[:mid])
    node.right = Node(data[mid:])
    assert node.value == data
    assert isinstance(node.left, Node) and isinstance(node.right, Node)


def test_create_root(root):
    assert root.root is None


def test_root_insert_even_data(root):
    data = range(4)
    root.insert(data)
    assert isinstance(root.root, Node)
    assert root.root.value == data

    assert isinstance(root.root.left, Node)
    assert root.root.left.value == data[:2]
    assert isinstance(root.root.left.left, Node)
    assert root.root.left.left.value == data[:1]
    assert root.root.left.left.left is None

    assert isinstance(root.root.right, Node)
    assert root.root.right.value == data[-2:]
    assert isinstance(root.root.right.right, Node)
    assert root.root.right.right.value == data[-1:]
    assert root.root.right.right.right is None


def test_root_insert_not_even_data(root):
    data = range(5)
    root.insert(data)
    assert isinstance(root.root, Node)
    assert root.root.value == data

    assert isinstance(root.root.left, Node)
    assert root.root.left.value == data[:2]
    assert isinstance(root.root.left.left, Node)
    assert root.root.left.left.value == data[:1]
    assert root.root.left.left.left is None

    assert isinstance(root.root.right, Node)
    assert root.root.right.value == data[-3:]
    assert isinstance(root.root.right.right, Node)
    assert root.root.right.right.value == data[-2:]
    assert isinstance(root.root.right.right.right, Node)
    assert root.root.right.right.right.value == data[-1:]
    assert root.root.right.right.right.right is None
