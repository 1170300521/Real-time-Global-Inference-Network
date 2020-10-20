#python code/main_dist.py "flickr_test"  --bs=16 --nw=4
python code/main_dist.py "flickr_test" --bs=16 --nw=4 --resume=True --only_val=True --only_test=True
#python code/main_dist.py "flickr_test"  --bs=16 --nw=4 --resume=True --resume_path="/home/wds/Downloads/flickr_try.pth" --only_val=True --only_test=True

