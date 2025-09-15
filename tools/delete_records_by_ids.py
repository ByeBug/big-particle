'''
删除记录脚本
根据给定条件查询记录ID，将记录、oss 记录、实际图片删除

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

from tools.utils import get_db_connection

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
    record_ids = [2187813, 2187812, 2182440, 2156470, 2130686, 2074784, 2055819, 2055528, 1977384,
1972341, 1958337, 1956565, 1952885, 1912733, 1906421, 1898357, 1894199, 1892674,
1886408]
    
    print('警告: 将要删除给定 id 的记录、OSS 记录和实际图片文件，此操作不可逆！')
    
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
        
        if not record_ids:
            print("未给定记录 id")
            return
        
        # 将记录ID转换为范围，便于分批处理
        record_ranges = []
        # 按1000个记录为一批进行分组
        batch_size = 1000
        for i in range(0, len(record_ids), batch_size):
            batch_record_ids = record_ids[i:i + batch_size]
            start_id = min(batch_record_ids)
            end_id = max(batch_record_ids)
            record_ranges.append((start_id, end_id, batch_record_ids))
        
        print(f"将分 {len(record_ranges)} 个批次处理")
        
        # 分批删除记录
        for range_idx, (start_id, end_id, batch_record_ids) in enumerate(record_ranges):
            print(f"\n处理批次 {range_idx + 1}/{len(record_ranges)}: {len(batch_record_ids)} 条记录 (ID范围: {start_id}-{end_id})")
            
            # 1. 获取当前批次的记录信息
            placeholders = ','.join(['%s'] * len(batch_record_ids))
            sql_select = f'''
            SELECT id, original_image_id, rendered_image_id, stream_name, detected_at
            FROM core_algo_record
            WHERE id IN ({placeholders})
            ORDER BY id DESC
            '''
            
            cursor.execute(sql_select, batch_record_ids)
            records = cursor.fetchall()
            
            if not records:
                print(f"\t批次中没有找到记录")
                continue
            
            print(f"\t找到 {len(records)} 条记录")
            
            # 收集图片ID
            batch_image_ids = set()
            
            for record in records:
                record_id, original_image_id, rendered_image_id, stream_name, detected_at = record
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
            sql_delete_records = f'''
            DELETE FROM core_algo_record
            WHERE id IN ({placeholders})
            '''
            
            cursor.execute(sql_delete_records, batch_record_ids)
            deleted_records_count = cursor.rowcount
            total_deleted_records += deleted_records_count
            print(f"\t删除 {deleted_records_count} 条算法记录")

            # 4. 删除当前批次的大颗粒详情记录
            sql_delete_big_particle_detail = f'''
            DELETE FROM algo_big_particle_detail
            WHERE record_id IN ({placeholders})
            '''
            
            cursor.execute(sql_delete_big_particle_detail, batch_record_ids)
            deleted_big_particle_detail_count = cursor.rowcount
            total_deleted_big_particle_detail += deleted_big_particle_detail_count
            print(f"\t删除 {deleted_big_particle_detail_count} 条大颗粒详情记录")
            
            # 每批次都提交事务
            conn.commit()
            print(f"\t批次 {range_idx + 1} 处理完成")
        
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
