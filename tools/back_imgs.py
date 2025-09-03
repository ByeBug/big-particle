'''
图片回流脚本
根据给定的记录ID列表，将对应的原图文件复制到指定的输出目录

使用方法:
python tools/back_imgs.py <起始ID1>-<结束ID1> [<起始ID2>-<结束ID2>] ...

示例:
python tools/back_imgs.py 100-200 300-400

文件命名规则: record_{记录ID}_original.{扩展名}
脚本会自动创建 {当前日期}_back 目录并复制文件
'''

import os
import sys
import shutil
import psycopg
from datetime import datetime

# 支持从项目根目录或 tools 目录执行
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))  # tools 目录
    project_root = os.path.dirname(script_dir)              # backend 目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from tools.utils import parse_record_ranges, get_db_connection

def main():
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python tools/back_imgs.py <起始ID1>-<结束ID1> [<起始ID2>-<结束ID2>] ...")
        print("示例: python tools/back_imgs.py 100-200 300-400")
        return
    
    # 解析记录ID范围
    record_ranges = parse_record_ranges(sys.argv[1:])
    
    if not record_ranges:
        print("错误: 没有有效的记录ID范围")
        print("请使用格式: 起始ID-结束ID，例如: 100-200")
        return
    
    # 生成当前日期格式的输出目录名
    current_date = datetime.now().strftime('%Y%m%d')
    output_dir = f'{current_date}_back'
    
    print(f'将回流以下ID范围的记录原图：')
    for start_id, end_id in record_ranges:
        print(f'{start_id} 到 {end_id}')
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")

    # 连接 postgres 数据库
    conn = get_db_connection()
    if not conn:
        return

    try:
        # 执行 sql 获取记录的 original_image_id
        cursor = conn.cursor()
        
        # 构建多个 BETWEEN 条件的 SQL
        between_conditions = []
        range_params = []
        
        for start_id, end_id in record_ranges:
            between_conditions.append("(id BETWEEN %s AND %s)")
            range_params.extend([start_id, end_id])
        
        sql1 = f'''
        SELECT id, original_image_id, stream_name, detected_at
        FROM algo_big_particle_record
        WHERE {' OR '.join(between_conditions)}
        ORDER BY id DESC
        '''
        
        print(f"执行SQL查询: {sql1}")
        print(f"参数: {range_params}")
        cursor.execute(sql1, range_params)
        records = cursor.fetchall()
        
        if not records:
            print("没有找到匹配的记录")
            return
            
        print(f"找到 {len(records)} 条记录")
        
        # 提取 original_image_id 列表，过滤掉 None 值
        original_image_ids = []
        record_info = {}  # 存储记录信息用于后续文件命名
        
        for record in records:
            record_id, original_image_id, stream_name, detected_at = record
            if original_image_id is not None:
                original_image_ids.append(original_image_id)
                record_info[original_image_id] = {
                    'record_id': record_id,
                    'stream_name': stream_name,
                    'detected_at': detected_at
                }
        
        if not original_image_ids:
            print("所有记录的 original_image_id 都为空")
            return
            
        print(f"有效的原图ID数量: {len(original_image_ids)}")

        # 执行 sql 获取文件路径
        placeholders2 = ','.join(['%s'] * len(original_image_ids))
        sql2 = f'''
        SELECT id, file_path, file_name, created_at
        FROM core_oss_object
        WHERE id IN ({placeholders2}) AND deleted_at IS NULL
        '''
        
        cursor.execute(sql2, original_image_ids)
        oss_objects = cursor.fetchall()
        
        if not oss_objects:
            print("没有找到对应的OSS对象")
            return
            
        print(f"找到 {len(oss_objects)} 个OSS对象")
        
        # 处理文件复制
        success_count = 0
        error_count = 0

        for oss_obj in oss_objects:
            oss_id, file_path, file_name, created_at = oss_obj
            abs_file_path = f'/data/big-particle-data/storage/oss/{file_path}'
            
            # 检查源文件是否存在
            if not os.path.exists(abs_file_path):
                print(f"源文件不存在: {abs_file_path}")
                error_count += 1
                continue
            
            new_filename = f"record_{record_info[oss_id]['record_id']}_original.{os.path.splitext(file_name)[1]}"
            target_path = os.path.join(output_dir, new_filename)
            
            try:
                # 复制文件到输出目录
                shutil.copy2(abs_file_path, target_path)
                print(f"成功复制: {new_filename}")
                success_count += 1
            except Exception as e:
                print(f"复制失败 {abs_file_path} -> {target_path}: {e}")
                error_count += 1
        
        print(f"\n回流完成:")
        print(f"  成功: {success_count} 个文件")
        print(f"  失败: {error_count} 个文件")
        print(f"  输出目录: {output_dir}")
        
    except psycopg.Error as e:
        print(f"数据库操作失败: {e}")
    except Exception as e:
        print(f"执行失败: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    main()
