'''
删除记录脚本
根据给定的记录ID范围，将记录、oss 记录、实际图片删除

使用方法:
python tools/delete_records.py <起始ID1>-<结束ID1> [<起始ID2>-<结束ID2>] ...

示例:
python tools/delete_records.py 100-200 300-400

注意: 此操作不可逆，请谨慎使用！
'''

import os
import sys
import psycopg

# 支持从项目根目录或 tools 目录执行
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))  # tools 目录
    project_root = os.path.dirname(script_dir)              # backend 目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from tools.utils import parse_record_ranges, get_db_connection

def delete_files_and_oss_records(cursor, image_ids):
    """删除文件和 OSS 记录"""
    deleted_files_count = 0
    failed_files_count = 0
    deleted_oss_count = 0
    
    if not image_ids:
        return deleted_files_count, failed_files_count, deleted_oss_count
    
    # 查询 OSS 记录（image_ids 最多 2000 个，无需分批）
    placeholders = ','.join(['%s'] * len(image_ids))
    sql_oss = f'''
    SELECT id, file_path, file_name
    FROM core_oss_object
    WHERE id IN ({placeholders})
    '''
    
    cursor.execute(sql_oss, image_ids)
    oss_objects = cursor.fetchall()
    
    print(f"\t\t找到 {len(oss_objects)} 个 OSS 记录")
    
    # 删除实际文件
    print(f"\t\t删除文件中...")
    for oss_obj in oss_objects:
        oss_id, file_path, file_name = oss_obj
        abs_file_path = f'/data/big-particle-data/storage/oss/{file_path}'
        
        try:
            if os.path.exists(abs_file_path):
                os.remove(abs_file_path)
                deleted_files_count += 1
            else:
                print(f"\t\t\t文件不存在，跳过: {file_path}")
        except Exception as e:
            print(f"\t\t\t删除文件失败 {file_path}: {e}")
            failed_files_count += 1
    print(f"\t\t删除文件完成")

    # 删除 OSS 记录
    sql_delete_oss = f'''
    DELETE FROM core_oss_object 
    WHERE id IN ({placeholders})
    '''
    
    cursor.execute(sql_delete_oss, image_ids)
    deleted_oss_count = cursor.rowcount
    print(f"\t\t删除 {deleted_oss_count} 条 OSS 记录")
    
    return deleted_files_count, failed_files_count, deleted_oss_count

def main():
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python tools/delete_records.py <起始ID1>-<结束ID1> [<起始ID2>-<结束ID2>] ...")
        print("示例: python tools/delete_records.py 100-200 300-400")
        print("注意: 删除操作不可逆，请谨慎使用！")
        return
    
    # 解析记录ID范围
    record_ranges = parse_record_ranges(sys.argv[1:])
    
    if not record_ranges:
        print("错误: 没有有效的记录ID范围")
        print("请使用格式: 起始ID-结束ID，例如: 100-200")
        return
    
    print('警告: 将要删除以下 ID 范围的记录、OSS 记录和实际图片文件，此操作不可逆！')
    for start_id, end_id in record_ranges:
        print(f'{start_id} 到 {end_id}')
    
    # 用户确认
    confirm = input("确认要继续删除操作吗？输入 'y' 继续: ")
    if confirm != 'y':
        print("操作已取消")
        return

    # 连接 postgres 数据库
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor()
        
        # 统计变量
        total_deleted_records = 0
        total_deleted_big_particle_detail = 0
        total_deleted_files = 0
        total_failed_files = 0
        total_deleted_oss = 0
        all_image_ids = set()
        
        print(f"开始分批处理删除操作...")
        
        # 分批处理每个范围
        for range_idx, (start_id, end_id) in enumerate(record_ranges):
            print(f"\n处理范围 {range_idx + 1}/{len(record_ranges)}: {start_id}-{end_id}")
            
            # 计算当前范围的总记录数
            range_size = end_id - start_id + 1
            
            # 分批处理当前范围
            for batch_start in range(start_id, end_id + 1, 1000):
                batch_end = min(batch_start + 999, end_id)
                print(f"\t处理批次: {batch_start}-{batch_end}")
                
                # 1. 获取当前批次的记录信息
                sql_select = '''
                SELECT id, original_image_id, rendered_image_id, stream_name, detected_at
                FROM core_algo_record
                WHERE id BETWEEN %s AND %s
                ORDER BY id DESC
                '''
                
                cursor.execute(sql_select, [batch_start, batch_end])
                records = cursor.fetchall()
                
                if not records:
                    print(f"\t\t批次 {batch_start}-{batch_end} 没有找到记录")
                    continue
                
                print(f"\t\t找到 {len(records)} 条记录")
                
                # 收集记录ID和图片ID
                batch_record_ids = []
                batch_image_ids = set()
                
                for record in records:
                    record_id, original_image_id, rendered_image_id, stream_name, detected_at = record
                    batch_record_ids.append(record_id)
                    if original_image_id is not None:
                        batch_image_ids.add(original_image_id)
                        all_image_ids.add(original_image_id)
                    if rendered_image_id is not None:
                        batch_image_ids.add(rendered_image_id)
                        all_image_ids.add(rendered_image_id)
                
                # 2. 删除当前批次的文件和 OSS 记录
                if batch_image_ids:
                    deleted_files, failed_files, deleted_oss = delete_files_and_oss_records(
                        cursor, list(batch_image_ids)
                    )
                    total_deleted_files += deleted_files
                    total_failed_files += failed_files
                    total_deleted_oss += deleted_oss
                
                # 3. 删除当前批次的算法记录
                sql_delete_records = '''
                DELETE FROM core_algo_record
                WHERE id BETWEEN %s AND %s
                '''
                
                cursor.execute(sql_delete_records, [batch_start, batch_end])
                deleted_records_count = cursor.rowcount
                total_deleted_records += deleted_records_count
                print(f"\t\t删除 {deleted_records_count} 条算法记录")

                # 4. 删除当前批次的大颗粒详情记录
                sql_delete_big_particle_detail = '''
                DELETE FROM algo_big_particle_detail
                WHERE record_id BETWEEN %s AND %s
                '''
                
                cursor.execute(sql_delete_big_particle_detail, [batch_start, batch_end])
                deleted_big_particle_detail_count = cursor.rowcount
                total_deleted_big_particle_detail += deleted_big_particle_detail_count
                print(f"\t\t删除 {deleted_big_particle_detail_count} 条大颗粒详情记录")
                
                # 每批次都提交事务
                conn.commit()
                print(f"\t\t批次 {batch_start}-{batch_end} 处理完成")
        
        print(f"\n所有删除操作完成:")
        print(f"\t删除记录数: {total_deleted_records} 条")
        print(f"\t删除大颗粒详情记录数: {total_deleted_big_particle_detail} 条")
        print(f"\t删除 OSS 记录数: {total_deleted_oss} 条")
        print(f"\t删除文件数: {total_deleted_files} 个")
        print(f"\t删除文件失败数: {total_failed_files} 个")
        
    except psycopg.Error as e:
        print(f"数据库操作失败: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"删除操作失败: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    main()
