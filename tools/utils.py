'''
工具脚本公共函数模块
包含各种脚本共用的实用函数
'''

def parse_record_ranges(args):
    """
    解析命令行参数为记录ID范围列表
    
    Args:
        args: 命令行参数列表，每个参数格式为 "起始ID-结束ID" 或 "结束ID-起始ID"
        
    Returns:
        list: 包含 (start_id, end_id) 元组的列表，自动规范化为正序（小-大）
        
    Example:
        >>> parse_record_ranges(['100-200', '400-300'])
        [(100, 200), (300, 400)]
    """
    record_ranges = []
    
    for arg in args:
        try:
            if '-' in arg:
                start_str, end_str = arg.split('-', 1)
                start_id = int(start_str.strip())
                end_id = int(end_str.strip())
                
                # 自动规范化为正序（小-大）
                if start_id > end_id:
                    start_id, end_id = end_id, start_id
                    print(f"提示: 将范围 {arg} 规范化为 {start_id}-{end_id}")
                
                record_ranges.append((start_id, end_id))
            else:
                print(f"警告: 跳过格式错误的参数 {arg} (应为 起始ID-结束ID)")
        except ValueError:
            print(f"警告: 跳过格式错误的参数 {arg} (ID必须为整数)")
    
    return record_ranges


def get_db_connection():
    """
    获取 PostgreSQL 数据库连接
    
    Returns:
        psycopg.Connection: 数据库连接对象，失败时返回 None
    """
    try:
        import psycopg
        conn = psycopg.connect(
            host="localhost",
            port=15432,
            user="bigparticle", 
            password="bigparticle",
            dbname="bigparticle"
        )
        return conn
    except ImportError:
        print("错误: 未安装 psycopg 库，请运行: pip install psycopg[binary]")
        return None
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return None
