
class Instance:
    '''模型结果实例'''
    def __init__(self, label_id: int, label_name: str, score: float,
                 left: float, top: float, right: float, bottom: float):
        self.label_id = label_id
        self.label_name = label_name
        self.score = score
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
