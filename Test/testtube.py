title: str = "我爱摇滚乐 第 23 期! 万能青年旅店~董亚千、姬赓、史立 & 杨友耕激情奉献！"
after: str = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in title)
print(after)