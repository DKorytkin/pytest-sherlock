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
    r"""
    The function draws schema of binary tree

    >>> tree = make_tee((0, 7))
    >>> draw_tree(tree)
              ____________________(0, 7)_____________________
             /                                               \
        __(0, 3)_________                         ________(3, 7)_________
       /                 \                       /                       \
    (0, 1)          __(1, 3)___             __(3, 5)___             __(5, 7)___
                   /           \           /           \           /           \
                (1, 2)      (2, 3)      (3, 4)      (4, 5)      (5, 6)      (6, 7)

    Parameters
    ----------
    node: Node

    Returns
    -------
    None
    """

    def _left_shift_lines(lines, width):
        return [line + width * " " for line in lines]

    def _right_shift_lines(lines, width):
        return [width * " " + line for line in lines]

    def _build_left_line(middle, width):
        # '       ______'
        template = "{0:>{space_width}}{0:_>{line_width}}"
        return template.format(
            "", space_width=middle + 1, line_width=width - middle - 1
        )

    def _build_right_line(middle, width):
        # '______       '
        template = "{0:_>{line_width}}{0:>{space_width}}"
        return template.format("", space_width=width - middle, line_width=middle)

    def _build_left_arrows(middle, width):
        # '      /      '
        template = "{0:>{left_width}}/{0:<{right_width}}"
        return template.format("", left_width=middle, right_width=width - middle - 1)

    def _build_right_arrows(middle, width):
        # '      \      '
        template = "{0:>{left_width}}\\{0:<{right_width}}"
        return template.format("", left_width=middle, right_width=width - middle - 1)

    def _count_lines(current_node):
        """
        Parameters
        ----------
        current_node: Node

        Returns
        -------
        tuple[list[str], int, int, int]
            list of strings, width, height, middle
        """
        current_value = str(current_node)
        current_value_width = len(current_value)
        line_middle = current_value_width // 2
        line_height = 1

        # No child.
        if current_node.right is None and current_node.left is None:
            return [current_value], current_value_width, line_height, line_middle

        # Only left child.
        if current_node.right is None:
            lines, width, height, middle = _count_lines(current_node.left)
            value_line = _build_left_line(middle, width) + current_value
            arrows_line = _build_left_arrows(middle, width)
            previous_lines = _left_shift_lines(lines, current_value_width)
            return (
                [value_line, arrows_line] + previous_lines,
                width + current_value_width,
                height + 2,
                width + line_middle,
            )

        # Only right child.
        if current_node.left is None:
            lines, width, height, middle = _count_lines(current_node.right)
            value_line = current_value + _build_right_line(middle, width)
            arrows_line = _build_right_arrows(middle, width)
            previous_lines = _right_shift_lines(lines, current_value_width)
            return (
                [value_line, arrows_line] + previous_lines,
                width + current_value_width,
                height + 2,
                line_middle,
            )

        # Two children.
        left, l_width, l_height, l_middle = _count_lines(current_node.left)
        right, r_width, r_height, r_middle = _count_lines(current_node.right)
        value_line = (
            _build_left_line(l_middle, l_width)
            + current_value
            + _build_right_line(r_middle, r_width)
        )

        arrows_line = (
            _build_left_arrows(l_middle, l_width)
            + current_value_width * " "
            + _build_right_arrows(r_middle, r_width)
        )
        if l_height < r_height:
            left += [l_width * " "] * (r_height - l_height)
        elif r_height < l_height:
            right += [r_width * " "] * (l_height - r_height)
        previous_lines = [
            a + current_value_width * " " + b for a, b in zip(left, right)
        ]
        return (
            [value_line, arrows_line] + previous_lines,
            l_width + r_width + current_value_width,
            max(l_height, r_height) + 2,
            l_width + current_value_width // 2,
        )

    all_lines, _, _, _ = _count_lines(node)
    print("\n".join(all_lines))


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
