

class Node(object):
    def __init__(self, items):
        self.items = items
        self.left = None
        self.right = None


class Root(object):
    def __init__(self):
        self.root = None

    def insert(self, items):
        if self.root is not None or items is None:
            return self.root
        self.root = Node(items)
        return self._insert(items, self.root)

    def _insert(self, items, current_root):
        mid = len(items) // 2
        if not items or mid == 0:
            return

        left = items[:mid]
        if left:
            current_root.left = Node(left)
            self._insert(left, current_root.left)

        right = items[mid:]
        if right:
            current_root.right = Node(right)
            self._insert(right, current_root.right)
