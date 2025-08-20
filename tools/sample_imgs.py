'''
给定一个目录，对该目录下的所有目录，每个采样最多 x 张图片，
复制到输出目录中
'''

import os
import shutil
import argparse
import random
from pathlib import Path
from typing import List


def get_image_files(directory: str) -> List[str]:
    """获取目录下所有图片文件"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
    image_files = []
    
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path) and Path(file).suffix.lower() in image_extensions:
            image_files.append(file_path)
    
    return image_files


def sample_images_from_directory(input_dir: str, output_dir: str, max_samples: int, random_seed: int = None):
    """
    从输入目录的各个子目录中采样图片并复制到输出目录
    
    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径  
        max_samples: 每个子目录最多采样的图片数量
        random_seed: 随机种子，确保结果可重现
    """
    if random_seed is not None:
        random.seed(random_seed)
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取输入目录下的所有子目录
    subdirs = []
    for item in os.listdir(input_dir):
        item_path = os.path.join(input_dir, item)
        if os.path.isdir(item_path):
            subdirs.append(item)
    
    if not subdirs:
        print(f"警告: 在 {input_dir} 中没有找到任何子目录")
        return
    
    total_copied = 0
    
    for subdir in subdirs:
        subdir_path = os.path.join(input_dir, subdir)
        output_subdir = os.path.join(output_dir, subdir)
        
        # 创建输出子目录
        os.makedirs(output_subdir, exist_ok=True)
        
        # 获取该子目录下的所有图片
        image_files = get_image_files(subdir_path)
        
        if not image_files:
            print(f"警告: 在 {subdir_path} 中没有找到任何图片文件")
            continue
        
        # 随机采样图片
        num_samples = min(max_samples, len(image_files))
        sampled_images = random.sample(image_files, num_samples)
        
        # 复制采样的图片到输出目录
        copied_count = 0
        for image_path in sampled_images:
            image_name = os.path.basename(image_path)
            output_path = os.path.join(output_subdir, image_name)
            
            try:
                shutil.copy2(image_path, output_path)
                copied_count += 1
            except Exception as e:
                print(f"错误: 复制文件 {image_path} 失败: {e}")
        
        print(f"从 {subdir} 复制了 {copied_count}/{len(image_files)} 张图片")
        total_copied += copied_count
    
    print(f"\n总共复制了 {total_copied} 张图片到 {output_dir}")


def main():
    parser = argparse.ArgumentParser(description='从输入目录的各个子目录中采样图片并复制到输出目录')
    parser.add_argument('input_dir', help='输入目录路径')
    parser.add_argument('output_dir', help='输出目录路径')
    parser.add_argument('max_samples', type=int, help='每个子目录最多采样的图片数量')
    parser.add_argument('--seed', type=int, default=None, help='随机种子（可选）')
    
    args = parser.parse_args()
    
    # 验证输入目录是否存在
    if not os.path.exists(args.input_dir):
        print(f"错误: 输入目录 {args.input_dir} 不存在")
        return
    
    if not os.path.isdir(args.input_dir):
        print(f"错误: {args.input_dir} 不是一个目录")
        return
    
    if args.max_samples <= 0:
        print("错误: 采样数量必须大于0")
        return
    
    print(f"输入目录: {args.input_dir}")
    print(f"输出目录: {args.output_dir}")
    print(f"每个子目录最大采样数: {args.max_samples}")
    if args.seed is not None:
        print(f"随机种子: {args.seed}")
    print("-" * 50)
    
    sample_images_from_directory(args.input_dir, args.output_dir, args.max_samples, args.seed)


if __name__ == "__main__":
    main()
