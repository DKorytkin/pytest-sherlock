

class Node(object):
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


class Root(object):
    def __init__(self):
        self.root = None

    def insert(self, value):
        if self.root is not None or value is None:
            return self.root
        self.root = Node(value)
        return self._insert(value, self.root)

    def _insert(self, value, current_root):
        mid = len(value) // 2
        if not value or mid == 0:
            return

        left = value[:mid]
        if left:
            current_root.left = Node(left)
            self._insert(left, current_root.left)

        right = value[mid:]
        if right:
            current_root.right = Node(right)
            self._insert(right, current_root.right)
