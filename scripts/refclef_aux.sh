python code/main_dist.py "referclef_aux" --ds_to_use='refclef' --bs=16 --nw=4 --epochs=20
#python code/main_dist.py "referclef_aux" --ds_to_use='refclef' --bs=8 --nw=4 --resume=True --resize_img="[608,608]"
#python code/main_dist.py "referclef_aux" --ds_to_use='refclef' --bs=16 --nw=4 --resume=True --resize_img="[608,608]" --only_val=True --only_test=True
#python code/main_dist.py "referclef_aux" --ds_to_use='refclef' --bs=32 --nw=4 --resume=True --resume_path="/home/wds/Downloads/referit_try.pth" --only_val=True --only_test=True
