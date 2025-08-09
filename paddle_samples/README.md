运行 paddle 推理

安装：
```sh
apt install ccache
uv add paddlepaddle-gpu==3.1.0 --index https://www.paddlepaddle.org.cn/packages/stable/cu126/ --index-strategy unsafe-best-match
```

命令：
```sh
export LD_LIBRARY_PATH=/home/vlight/dev/TensorRT-10.5.0.18/lib:$LD_LIBRARY_PATH
python my_infer.py --model_dir=models/big_particle_trt --image_dir=test_data/tmp_test --device=gpu --run_mode=trt_fp16 --output_dir=tmp4 --batch_size=4
```

脚本会加载模型目录下的 trt 缓存
