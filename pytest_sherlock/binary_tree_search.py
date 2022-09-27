class Node(object):
    def __init__(self, items, left=None, right=None):
        self.items = self.validate(items)
        self.left = left
        self.right = right

    def __str__(self):
        return str(self.items)

    def __repr__(self):
        return "<Node {}>".format(self.items)

    @staticmethod
    def validate(items):
        if not isinstance(items, tuple):
            raise RuntimeError(
                "Must be tuple with indices, (start, end): {}".format(items)
            )
        if len(items) != 2:
            raise RuntimeError(
                "Must contain (start, end) indices of tests: {}".format(items)
            )

        start, end = items
        if not isinstance(start, int) or not isinstance(end, int):
            raise RuntimeError("Indices must be integer: {}".format(items))
        if start < 0:
            raise RuntimeError(
                "Invalid start index must be started from 0 or greater: {}".format(
                    items
                )
            )
        if start >= end:
            raise RuntimeError(
                "Invalid end index must be greater than start: {}".format(items)
            )
        return items


def draw_tree(node):
    def _count_lines(current_node):
        """Returns list of strings, width, height, and horizontal coordinate of the root."""
        line = str(current_node)
        line_width = len(line)
        line_middle = line_width // 2
        line_height = 1

        # No child.
        if current_node.right is None and current_node.left is None:
            return [line], line_width, line_height, line_middle

        # Only left child.
        if current_node.right is None:
            lines, width, height, middle = _count_lines(current_node.left)
            first_line = (middle + 1) * " " + (width - middle - 1) * "_" + line
            second_line = middle * " " + "/" + (width - middle - 1 + line_width) * " "
            shifted_lines = [line + line_width * " " for line in lines]
            return (
                [first_line, second_line] + shifted_lines,
                width + line_width,
                height + 2,
                width + line_middle,
            )

        # Only right child.
        if current_node.left is None:
            lines, width, height, middle = _count_lines(current_node.right)
            first_line = line + middle * "_" + (width - middle) * " "
            second_line = (
                (line_width + middle) * " " + "\\" + (width - middle - 1) * " "
            )
            shifted_lines = [line_width * " " + line for line in lines]
            return (
                [first_line, second_line] + shifted_lines,
                width + line_width,
                height + 2,
                line_middle,
            )

        # Two children.
        left, l_width, l_height, l_middle = _count_lines(current_node.left)
        right, r_width, r_height, r_middle = _count_lines(current_node.right)
        first_line = (
            (l_middle + 1) * " "
            + (l_width - l_middle - 1) * "_"
            + line
            + r_middle * "_"
            + (r_width - r_middle) * " "
        )
        second_line = (
            l_middle * " "
            + "/"
            + (l_width - l_middle - 1 + line_width + r_middle) * " "
            + "\\"
            + (r_width - r_middle - 1) * " "
        )
        if l_height < r_height:
            left += [l_width * " "] * (r_height - l_height)
        elif r_height < l_height:
            right += [r_width * " "] * (l_height - r_height)
        zipped_lines = zip(left, right)
        lines = [first_line, second_line] + [
            a + line_width * " " + b for a, b in zipped_lines
        ]
        return (
            lines,
            l_width + r_width + line_width,
            max(l_height, r_height) + 2,
            l_width + line_width // 2,
        )

    all_lines, _, _, _ = _count_lines(node)
    for line in all_lines:
        print(line)


def make_tee(items):
    """
    Parameters
    ----------
    items: tuple[int, int]
        (0, 21) - (start, end) indices of tests

    Returns
    -------
    Node
        Root node of tree
    """

    def _insert(items, current_root):
        """
        Parameters
        ----------
        items: tuple[int, int]
            (0, 21)
        current_root: Node

        Returns
        -------
        None
        """
        start, end = items
        if start >= end - 1:
            return

        middle = start + (end - start) // 2
        if start < middle:
            left_range = (start, middle)
            current_root.left = Node(left_range)
            _insert(left_range, current_root.left)

        if middle < end:
            right_range = (middle, end)
            current_root.right = Node(right_range)
            _insert(right_range, current_root.right)

    root = Node(items)
    _insert(items, root)
    return root


def length(node, func=max):
    def count_length(current_node):
        if current_node is None:
            return 0

        left = count_length(current_node.left)
        right = count_length(current_node.right)
        return func([left, right]) + 1

    if node is None:
        return 0

    increment = 0 if func is max else -1  # exclude root
    return count_length(node) + increment
