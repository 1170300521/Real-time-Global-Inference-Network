#python code/main_dist.py "refclef" --ds_to_use='refclef' --bs=16 --nw=4 --epochs=20
#python code/main_dist.py "refclef" --ds_to_use='refclef' --bs=8 --nw=4 --resume=True --resize_img="[608,608]"
python code/main_dist.py "refclef" --ds_to_use='refclef' --bs=16 --nw=4 --resume=True --resize_img="[416, 416]" --only_val=True --lstm_dim=128 --img_dim=256 --lang_to_use="lstm"
#CUDA_VISIBLE_DEVICES=0,1 python code/main_dist.py "refclef" --ds_to_use='refclef' --bs=32 --nw=4 --resume=True --resume_path="/home/wds/Downloads/referit_try.pth" --only_val=True --only_test=True
