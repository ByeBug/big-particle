'''
统计日期范围内每天的颗粒数量统计
按照不同尺寸范围统计颗粒数量
'''
import os
import sys
from datetime import datetime, timedelta

# 支持从项目根目录或 tools 目录执行
if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))  # tools 目录
    project_root = os.path.dirname(script_dir)              # backend 目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from tools.utils import get_db_connection


def get_particle_size_stats_by_day(stream_ids, start_date, end_date, size_levels):
    """
    获取指定日期范围内按天分组的颗粒尺寸统计
    
    Args:
        stream_ids: 流ID列表
        start_date: 开始日期
        end_date: 结束日期
        size_levels: 尺寸等级列表，如 [25, 32, 45, 60, 73, 92]
    
    Returns:
        查询结果列表，包含天信息和动态尺寸统计
    """
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        with conn.cursor() as cur:
            # 构建SQL查询，按天分组
            stream_ids_str = ','.join(map(str, stream_ids))
            
            # 动态构建尺寸范围的COUNT语句
            count_clauses = []
            for i in range(len(size_levels)):
                if i == len(size_levels) - 1:
                    # 最后一个范围：>= last_level
                    count_clauses.append(f"COUNT(CASE WHEN size >= {size_levels[i]} THEN 1 END) AS count_{i}")
                else:
                    # 其他范围：>= current_level AND < next_level
                    count_clauses.append(f"COUNT(CASE WHEN size >= {size_levels[i]} AND size < {size_levels[i+1]} THEN 1 END) AS count_{i}")
            
            count_sql = ',\n                '.join(count_clauses)

            count_sql = count_sql.replace('size', 'short_size')
            
            sql = f"""
            SELECT 
                stream_id,
                DATE_TRUNC('day', detected_at) AS date,
                {count_sql}
            FROM algo_big_particle_detail
            WHERE stream_id IN ({stream_ids_str})
            AND detected_at >= %s AND detected_at < %s
            GROUP BY stream_id, DATE_TRUNC('day', detected_at)
            ORDER BY stream_id, date
            """

            # print(sql)
            
            cur.execute(sql, (start_date, end_date))
            results = cur.fetchall()
            return results
            
    except Exception as e:
        print(f"查询失败: {e}")
        return None
    finally:
        conn.close()


def print_stats_table(results, size_levels):
    """
    格式化输出按天统计的结果
    """
    
    # 动态生成列标题
    headers = ['stream_id', 'date']
    for i in range(len(size_levels)):
        if i == len(size_levels) - 1:
            headers.append(f'>={size_levels[i]}mm')
        else:
            headers.append(f'{size_levels[i]}-{size_levels[i+1]}mm')
    headers.append('total')
    
    # 计算总宽度
    col_width = 17
    total_width = len(headers) * col_width
    
    print("=" * total_width)
    
    # 输出表头
    header_line = ""
    for header in headers:
        header_line += f"{header:<{col_width}}"
    print(header_line)
    print("-" * total_width)
    
    # 初始化统计变量
    num_size_ranges = len(size_levels)
    daily_totals = [0] * (num_size_ranges + 1)  # +1 for total_count
    current_stream = None
    stream_totals = [0] * (num_size_ranges + 1)
    
    for row in results:
        # 解析行数据：stream_id, date, count_0, count_1, ..., total_count
        stream_id = row[0]
        date = row[1]
        counts = list(row[2:2+num_size_ranges])  # 各尺寸范围的计数
        total_count = sum(counts)  # 最后一列是总计
        
        # 如果是新的流ID，先输出上一个流的小计
        if current_stream is not None and current_stream != stream_id:
            line = f"{'stm_total':<{col_width}}{'':>{col_width}}"
            for total in stream_totals:
                line += f"{total:<{col_width}}"
            print(line)
            print("-" * total_width)
            # 重置流统计
            stream_totals = [0] * (num_size_ranges + 1)
        
        current_stream = stream_id
        date_str = date.strftime('%Y-%m-%d')
        
        # 输出数据行
        line = f"{stream_id:<{col_width}}{date_str:<{col_width}}"
        for count in counts:
            percentage = round((count / total_count * 100), 2) if total_count > 0 else 0.0
            count_and_percentage = f"{count}({percentage}%)"
            line += f"{count_and_percentage:<{col_width}}"
        line += f"{total_count:<{col_width}}"
        print(line)
        
        # 累加统计
        for i, count in enumerate(counts):
            stream_totals[i] += count
            daily_totals[i] += count
        stream_totals[-1] += total_count
        daily_totals[-1] += total_count
    
    # 输出最后一个流的小计
    if current_stream is not None:
        line = f"{'stm_total':<{col_width}}{'':>{col_width}}"
        for total in stream_totals:
            line += f"{total:<{col_width}}"
        print(line)
        print("-" * total_width)


if __name__ == '__main__':
    stream_ids = [1]
    size_levels = [35, 40, 45, 55, 60, 73, 92]
    date_range = ['20250907', '20250919']
    
    print(f"开始统计流ID: {stream_ids}")
    print(f"统计日期: [{date_range[0]}, {date_range[1]})")
    print("按每天分组统计颗粒尺寸分布...")

    # 执行按天分组的查询
    results = get_particle_size_stats_by_day(stream_ids, date_range[0], date_range[1], size_levels)
        
    if results is None:
        print(f"查询失败")
        exit(1)
        
    # 输出结果
    print_stats_table(results, size_levels)
    
    print("\n统计完成！")
