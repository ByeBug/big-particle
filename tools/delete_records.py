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
        
        # 构建多个 BETWEEN 条件的 SQL
        between_conditions = []
        range_params = []
        
        for start_id, end_id in record_ranges:
            between_conditions.append("(id BETWEEN %s AND %s)")
            range_params.extend([start_id, end_id])
        
        # 1. 首先获取要删除的记录信息
        sql_select = f'''
        SELECT id, original_image_id, rendered_image_id, stream_name, detected_at
        FROM algo_big_particle_record
        WHERE {' OR '.join(between_conditions)}
        ORDER BY id DESC
        '''
        
        print(f"查询要删除的记录...")
        cursor.execute(sql_select, range_params)
        records = cursor.fetchall()
        
        if not records:
            print("没有找到匹配的记录")
            return
            
        print(f"找到 {len(records)} 条记录准备删除")
        
        record_ids = []
        all_image_id_set = set()
        
        for record in records:
            record_id, original_image_id, rendered_image_id, stream_name, detected_at = record
            record_ids.append(record_id)
            if original_image_id is not None:
                all_image_id_set.add(original_image_id)
            if rendered_image_id is not None:
                all_image_id_set.add(rendered_image_id)
        
        print(f"记录 ID 数量: {len(record_ids)}")
        print(f"有效的图片 ID 数量: {len(all_image_id_set)}")

        # 2. 合并所有需要删除的图片ID
        all_image_ids = list(all_image_id_set)  # 去重
        deleted_files_count = 0
        failed_files_count = 0
        deleted_oss_count = 0
        
        if all_image_ids:
            placeholders = ','.join(['%s'] * len(all_image_ids))
            sql_oss = f'''
            SELECT id, file_path, file_name
            FROM core_oss_object
            WHERE id IN ({placeholders})
            '''
            
            cursor.execute(sql_oss, all_image_ids)
            oss_objects = cursor.fetchall()
            
            print(f"找到 {len(oss_objects)} 个 OSS 对象需要删除（包括原图和渲染图）")
            
            # 删除实际文件
            for oss_obj in oss_objects:
                oss_id, file_path, file_name = oss_obj
                abs_file_path = f'/data/big-particle-data/storage/oss/{file_path}'
                
                try:
                    if os.path.exists(abs_file_path):
                        os.remove(abs_file_path)
                        print(f"已删除文件: {file_path}")
                        deleted_files_count += 1
                    else:
                        print(f"文件不存在，跳过: {abs_file_path}")
                except Exception as e:
                    print(f"删除文件失败 {abs_file_path}: {e}")
                    failed_files_count += 1

            # 3. 硬删除OSS记录
            sql_delete_oss = f'''
            DELETE FROM core_oss_object 
            WHERE id IN ({placeholders})
            '''
            
            cursor.execute(sql_delete_oss, all_image_ids)
            deleted_oss_count = cursor.rowcount
            print(f"已硬删除 {deleted_oss_count} 条 OSS 记录")

        # 4. 删除算法记录
        sql_delete_records = f'''
        DELETE FROM algo_big_particle_record
        WHERE {' OR '.join(between_conditions)}
        '''
        
        cursor.execute(sql_delete_records, range_params)
        deleted_records_count = cursor.rowcount
        
        # 提交事务
        conn.commit()
        
        print(f"\n删除操作完成:")
        print(f"  删除记录数: {deleted_records_count} 条")
        print(f"  删除 OSS 记录数: {deleted_oss_count} 条")
        print(f"  删除文件数: {deleted_files_count} 个")
        print(f"  文件删除失败数: {failed_files_count} 个")
        print(f"  总图片 ID 数: {len(all_image_ids)} 个（原图+渲染图去重后）")
        
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
