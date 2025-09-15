'''
通过 tcp 连接到灯控制器
'''

import socket
import sys


def create_tcp_client():
    """创建TCP客户端连接"""
    host = '192.168.1.101'
    port = 4196  # 默认使用Modbus端口，如果需要其他端口请修改
    
    try:
        # 创建socket对象
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        # 连接到服务器
        print(f"正在连接到 {host}:{port}...")
        client_socket.connect((host, port))
        print(f"成功连接到 {host}:{port}")
        
        return client_socket
        
    except ConnectionRefusedError:
        print(f"连接被拒绝：无法连接到 {host}:{port}")
        return None
    except socket.timeout:
        print("连接超时")
        return None
    except Exception as e:
        print(f"连接失败：{e}")
        return None


def send_command(client_socket, command_bytes):
    """发送命令到服务器"""
    try:
        client_socket.send(command_bytes)
        print(f"已发送命令: {' '.join([f'{b:02X}' for b in command_bytes])}")
        
        # 可选：接收响应
        try:
            client_socket.settimeout(1.0)  # 设置1秒超时
            response = client_socket.recv(1024)
            if response:
                print(f"收到响应: {' '.join([f'{b:02X}' for b in response])}")
        except socket.timeout:
            print("没有收到响应（超时）")
        except Exception as e:
            print(f"接收响应时出错：{e}")
            
    except Exception as e:
        print(f"发送命令失败：{e}")


def main():
    """主函数"""
    print("灯控制器TCP客户端")
    print("使用说明：")
    print("- 输入 'o' 发送开灯命令")
    print("- 输入 'f' 发送关灯命令") 
    print("- 输入 'q' 退出程序")
    print("-" * 40)
    
    # 创建TCP连接
    client_socket = create_tcp_client()
    if not client_socket:
        print("无法建立连接，程序退出")
        return
    
    # 定义命令
    # 第一路
    command_on = bytes([0x01, 0x05, 0x00, 0x00, 0xFF, 0x00, 0x8C, 0x3A])  # 开灯命令
    command_off = bytes([0x01, 0x05, 0x00, 0x00, 0x00, 0x00, 0xCD, 0xCA])  # 关灯命令
    # 第二路
    command_on = bytes([0x01, 0x05, 0x00, 0x01, 0xFF, 0x00, 0xDD, 0xFA])  # 开灯命令
    command_off = bytes([0x01, 0x05, 0x00, 0x01, 0x00, 0x00, 0x9C, 0x0A])  # 关灯命令
    try:
        while True:
            try:
                # 读取用户输入
                user_input = input("\n请输入命令 (o=开灯, f=关灯, q=退出): ").strip().lower()
                
                if user_input == 'o':
                    print("发送开灯命令...")
                    send_command(client_socket, command_on)
                    
                elif user_input == 'f':
                    print("发送关灯命令...")
                    send_command(client_socket, command_off)
                    
                elif user_input == 'q':
                    print("正在退出...")
                    break
                    
                else:
                    print("无效输入，请输入 'o'、'f' 或 'q'")
                    
            except KeyboardInterrupt:
                print("\n检测到 Ctrl+C，正在退出...")
                break
                
    except Exception as e:
        print(f"程序运行出错：{e}")
        
    finally:
        # 关闭连接
        try:
            client_socket.close()
            print("连接已关闭")
        except:
            pass


if __name__ == "__main__":
    main()
