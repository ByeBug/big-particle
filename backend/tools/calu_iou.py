'''
计算两个检测框的 IoU
'''

def calc_iou(box1, box2):
    '''
    计算两个检测框的 IoU
    box格式: [x1, y1, x2, y2]，其中(x1,y1)是左上角，(x2,y2)是右下角
    '''
    x1, y1, x2, y2 = box1
    x3, y3, x4, y4 = box2
    
    # 计算交集区域的坐标
    inter_x1 = max(x1, x3)
    inter_y1 = max(y1, y3)
    inter_x2 = min(x2, x4)
    inter_y2 = min(y2, y4)
    
    # 计算交集面积
    inter_width = max(0, inter_x2 - inter_x1)
    inter_height = max(0, inter_y2 - inter_y1)
    inter_area = inter_width * inter_height
    
    # 计算两个框的面积
    area1 = (x2 - x1) * (y2 - y1)
    area2 = (x4 - x3) * (y4 - y3)
    
    # 计算并集面积
    union_area = area1 + area2 - inter_area
    
    # 计算IoU
    if union_area == 0:
        return 0
    
    iou = inter_area / union_area
    return iou

if __name__ == '__main__':
    box1 = [1205, 682, 1261, 727]
    box2 = [1203, 689, 1261, 734]
    print(round(calc_iou(box1, box2), 2))
