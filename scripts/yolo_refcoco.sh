python code/main_dist.py "yolo_refcoco" --ds_to_use='refcoco' --bs=14 --nw=4 --epochs=20 --mdl_to_use="realgin" --resize_img="[320, 320]" --relation=False
#python code/main_dist.py "yolo_refcoco" --ds_to_use='refcoco' --bs=16 --nw=4 --epochs=20 --mdl_to_use="realgin" --resume=True --load_opt=True --only_val=True --relation=False
#python code/main_dist.py "yolo_refcoco" --ds_to_use='refcoco' --bs=8 --nw=4 --resume=True --resize_img="[608,608]" --mdl_to_use="realgin" --relation=False
#python code/main_dist.py "yolo_refcoco" --ds_to_use='refcoco' --bs=16 --nw=4 --resume=True --resize_img="[608,608]" --only_val=True --only_test=True --mdl_to_use="realgin" --relation=False
