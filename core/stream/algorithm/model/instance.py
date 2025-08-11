
class Instance:
    '''模型结果实例'''
    def __init__(self, label_id: int, label_name: str, score: float,
                 left: int, top: int, right: int, bottom: int):
        self.label_id = label_id
        self.label_name = label_name
        self.score = score
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
