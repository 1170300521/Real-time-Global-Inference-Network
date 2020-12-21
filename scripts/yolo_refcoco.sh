python code/main_dist.py "mcn_refcoco" --ds_to_use='refcoco' --bs=16 --nw=8 --epochs=80 --mdl_to_use="realgin"
#python code/main_dist.py "mcn_refcoco" --ds_to_use='refcoco' --bs=16 --nw=4 --epochs=20 --mdl_to_use="realgin" --resume=False --load_opt=True --only_val=True
#python code/main_dist.py "mcn_refcoco" --ds_to_use='refcoco' --bs=8 --nw=4 --resume=True --resize_img="[608,608]" --mdl_to_use="realgin"
#python code/main_dist.py "mcn_refcoco" --ds_to_use='refcoco' --bs=16 --nw=4 --resume=True --resize_img="[608,608]" --only_val=True --only_test=True --mdl_to_use="realgin"
