'''
图片回流脚本
根据给定的过滤条件，获取记录ID列表，将对应的原图文件复制到指定的输出目录

文件命名规则: 使用 oss 记录中 file_path 中的文件名
脚本会自动创建 {当前日期}_back 目录并复制文件
'''

import os
import sys
import shutil
import random
import psycopg
from datetime import datetime

# 支持从项目根目录或 tools 目录执行
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))  # tools 目录
    project_root = os.path.dirname(script_dir)              # backend 目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from tools.utils import get_db_connection

def main():

    stream_id = 1
    min_size = 50
    max_size = 59
    start_time = '2025-09-02 00:00:00'
    end_time = None

    # 采样数量，记录数太多时进行采样
    sample_count = 400

    print('=' * 50)
    print(f'将回流以下过滤条件的记录原图：')
    print(f'stream_id: {stream_id}')
    print(f'min_size: {min_size}')
    print(f'max_size: {max_size}')
    print(f'start_time: {start_time}')
    print(f'end_time: {end_time}')
    print('=' * 50)

    # 生成当前日期格式的输出目录名
    current_date = datetime.now().strftime('%Y%m%d')
    output_dir = f'{current_date}_back'
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")

    # 连接 postgres 数据库
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        
        big_particle_select_sql = '''
        select distinct record_id from algo_big_particle_detail
        where stream_id = %s
        '''
        sql_params = [stream_id]
        if min_size is not None:
            big_particle_select_sql += ' and size >= %s'
            sql_params.append(min_size)
        if max_size is not None:
            big_particle_select_sql += ' and size <= %s'
            sql_params.append(max_size)
        if start_time is not None:
            big_particle_select_sql += ' and detected_at >= %s'
            sql_params.append(start_time)
        if end_time is not None:
            big_particle_select_sql += ' and detected_at < %s'
            sql_params.append(end_time)

        cursor.execute(big_particle_select_sql, sql_params)
        record_ids = cursor.fetchall()
        record_ids = [record_id for record_id, in record_ids]
        
        if not record_ids:
            print("没有找到匹配的大颗粒记录")
            return
            
        print(f"找到 {len(record_ids)} 个记录ID")
        
        if sample_count is not None:
            record_ids = random.sample(record_ids, sample_count)
            print(f"采样 {len(record_ids)} 个记录ID")

        # 构建 algo_record 查询的占位符和参数
        placeholders = ','.join(['%s'] * len(record_ids))
        algo_record_select_sql = f'''
        SELECT id, original_image_id, stream_name, detected_at
        FROM core_algo_record
        WHERE id IN ({placeholders})
        ORDER BY id DESC
        '''
        
        print(f"执行SQL查询获取算法记录...")
        cursor.execute(algo_record_select_sql, record_ids)
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
        SELECT id, file_path
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
            oss_id, file_path = oss_obj
            abs_file_path = f'/data/big-particle-data/storage/oss/{file_path}'
            
            # 检查源文件是否存在
            if not os.path.exists(abs_file_path):
                print(f"源文件不存在: {abs_file_path}")
                error_count += 1
                continue
            
            file_name = os.path.basename(file_path)
            target_path = os.path.join(output_dir, file_name)
            
            try:
                # 复制文件到输出目录
                shutil.copy2(abs_file_path, target_path)
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
