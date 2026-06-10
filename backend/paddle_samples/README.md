运行 paddle 推理

安装：
```sh
apt install ccache
uv pip install paddlepaddle-gpu==3.1.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
```

命令：
```sh
export LD_LIBRARY_PATH=/home/vlight/dev/TensorRT-10.5.0.18/lib:$LD_LIBRARY_PATH
python my_infer.py \
  --device=gpu --run_mode=trt_fp16 --batch_size=4 \
  --model_dir=models/big_particle_trt \
  --image_dir=test_data/tmp_test \
  --output_dir=output/tmp
```

脚本会加载模型目录下的 trt 缓存
