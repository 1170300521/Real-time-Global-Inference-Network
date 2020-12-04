python code/main_dist.py "baseline" --ds_to_use='refcoco' --bs=32 --nw=8 --epochs=20 --mdl_to_use="baseline" --resize_img="[320, 320]" --use_att_loss=False
#python code/main_dist.py "baseline" --ds_to_use='refcoco' --bs=16 --nw=4 --epochs=20 --mdl_to_use="baseline" --resume=True --load_opt=True --only_val=True --relation=False
#python code/main_dist.py "baseline" --ds_to_use='refcoco' --bs=8 --nw=4 --resume=True --resize_img="[608,608]" --mdl_to_use="baseline" --relation=False
#python code/main_dist.py "baseline" --ds_to_use='refcoco' --bs=16 --nw=4 --resume=True --resize_img="[608,608]" --only_val=True --only_test=True --mdl_to_use="baseline" --relation=False
