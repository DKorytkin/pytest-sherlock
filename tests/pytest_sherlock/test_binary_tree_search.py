import pytest

from pytest_sherlock.binary_tree_search import Node, Root


@pytest.fixture()
def root():
    return Root()


def test_create_node_with_default_params():
    data = range(3)
    node = Node(data)
    assert node.items == data
    assert node.left is None and node.right is None


def test_modify_node_prams():
    data = range(3)
    node = Node(data)
    mid = len(data) // 2
    node.left = Node(data[:mid])
    node.right = Node(data[mid:])
    assert node.items == data
    assert isinstance(node.left, Node) and isinstance(node.right, Node)


def test_create_root(root):
    assert root.root is None


def test_root_insert_even_data(root):
    data = range(4)
    root.insert(data)
    assert isinstance(root.root, Node)
    assert root.root.items == data

    assert isinstance(root.root.left, Node)
    assert root.root.left.items == data[:2]
    assert isinstance(root.root.left.left, Node)
    assert root.root.left.left.items == data[:1]
    assert root.root.left.left.left is None

    assert isinstance(root.root.right, Node)
    assert root.root.right.items == data[-2:]
    assert isinstance(root.root.right.right, Node)
    assert root.root.right.right.items == data[-1:]
    assert root.root.right.right.right is None


def test_root_insert_not_even_data(root):
    data = range(5)
    root.insert(data)
    assert isinstance(root.root, Node)
    assert root.root.items == data

    assert isinstance(root.root.left, Node)
    assert root.root.left.items == data[:2]
    assert isinstance(root.root.left.left, Node)
    assert root.root.left.left.items == data[:1]
    assert root.root.left.left.left is None

    assert isinstance(root.root.right, Node)
    assert root.root.right.items == data[-3:]
    assert isinstance(root.root.right.right, Node)
    assert root.root.right.right.items == data[-2:]
    assert isinstance(root.root.right.right.right, Node)
    assert root.root.right.right.right.items == data[-1:]
    assert root.root.right.right.right.right is None


def test_root_insert_without_data(root):
    root.insert(None)
    assert root.root is None


def test_root_length(root):
    root.insert(range(4))
    assert len(root) == 2


def test_not_even_root_length(root):
    root.insert(range(5))
    assert len(root) == 3
