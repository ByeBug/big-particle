
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
        self.id = 0     # 单帧中实例 id
    
    def to_dict(self):
        '''转换为字典格式'''
        return {
            'id': self.id,
            'label_id': self.label_id,
            'label_name': self.label_name,
            'score': round(self.score, 2),
            'left': self.left,
            'top': self.top,
            'right': self.right,
            'bottom': self.bottom,
        }
