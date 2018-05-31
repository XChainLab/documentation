对于任意ASCII 字符a, 任意的单ASCII字符与a相同的前缀位(prefix)可以用异或计算， 计算结果对照表如下

prefix位长 | 可能的取值数目 | 异或结果范围 
------ | ------ | ------ 
 8 | 0 | 0 
 7 | pow(2,0) | 1 
 6 | pow(2,1) | [2, 3]   
 5 | pow(2,2) | [4, 7] 
 4 | pow(2,3) | [8,15] 
 3 | pow(2,4) | [16, 31]
 2 | pow(2,5) | [32, 63]
 1 | pow(2,6) | [64, 127]
 0 | pow(2,7) | [128, 255] 
 
举个栗子 若 a^b = 5， 对照上表的异或范围a,b 的相同前缀有5个， 验证下 a=248, b=253, a^b =5, bin(a) = "0b1111,1000", bin(b)="0b1111,1101"

对于任意ASCII字符串a, 任意与其长度相同的ASCII字符串与a的前缀(prefix)位长可以通过迭代计算每个字节的累加得出， 

我们定义相同长度的ASCII字符串a,b 的距离为a的位长减前缀的位长 
+ 若a,b单字节， 则distance(a,b) = 8-length(prefix)
+ 若a,b是相同长度的字符串， 则distance(a, b) = length(a)*8 - length(prefix)
算法实现如下(golang版)

```python
func prefixLength(xor uint8) uint {
	switch {
	case xor == 1:
		return 7
	case xor >= 2 && xor <= 3:
		return 6
	case xor >= 4 && xor <= 7:
		return 5
	case xor >= 8 && xor <= 15:
		return 4
	case xor >= 16 && xor <= 31:
		return 3
	case xor >= 32 && xor <= 63:
		return 2
	case xor >= 64 && xor <= 127:
		return 1
	case xor >= 128 && xor <= 255:
		return 0
	}
	return 8
}

func calcDistance(a, b []byte) uint {
	c := uint(0)
	for i := 0; i < len(a) && i < len(b); i++ {
		x := a[i] ^ b[i]
		if x == 0 {
			c += 8
		} else {
			c += prefixLength(x)
			break
		}
	}
	return uint(len(a))*8 - c

}
```

Kademlia算法作为路由算法来发现节点或者Topic的基本步骤分为三步
1： 注册 Topic (可以是自己的ID或者想要分享给别人的某篇文章的关键字的hash值)
2： 广播 topic table， 同时保存接收到的table
3:  处理搜索请求(接受)， 
4： 返回找到目标topic对应的IP， 或者与目标topic 距离最近的几个点
下面给出个简易的实现

```python
const (
	EntriesLength               = 256
	NodesLengthPerEntry         = 20
	ReplacementesLengthPerEntry = 20
	TopicMaxIdleTime            = 10 * time.Second
	EntryGCInterval             = 20 * time.Second
)
type Topic [32]byte
type Node struct {
	topic    Topic  // topic, nodeId.....
	data     []byte // 可以是ip或者其他的任何东西 
	weight   uint // topic 的权重, 最简单的可以通过计算与目标机的链接时间得出
	lastUsed time.Time // slot满的时候用来删除
}
type Nodes []*Node // 按照weight排序的list需要实现heap.Interface
//implement heap interface, meth: Push/Pop/Less/Swap/Len

type entry struct {
	nodes         *Nodes 
	replacementes *Nodes
	lastGCTime    time.Time
}

type Table struct {
	topic   Topic //nodeID 
	entries []*entry // topic table ， length等于最远距离, 通过计算接受的topic与自己的topic 计算距离， 最远距离为8 * len(topic)
}

func NewTable(t Topic) *Table {
//  initialize
}

func (tbl *Table) Add(t Topic, weight uint, data []byte) {
	dis := calcDistance(tbl.topic, t)
	tbl.entries[dis].add(t, weight, data)
}

func (e *entry) add(t Topic, weight uint, data []byte) {
	n := new(Node)
	n.data = data
	n.topic = t
	n.lastUsed = time.Now()
	n.weight = weight
	if e.nodes.Len() < NodesLengthPerEntry {
		heap.Push(e.nodes, n)
		return
	}
	if e.replacementes.Len() > 0 {
		if (*(e.nodes))[0].weight < weight {
			nn := heap.Pop(e.nodes)
			heap.Push(e.nodes, n)
			n = nn.(*Node)
		}
	}
	heap.Push(e.replacementes, n)
	if e.replacementes.Len() == ReplacementesLengthPerEntry {
		heap.Pop(e.replacementes)
	}
	go e.gc()
}

func (e *entry) gc() {
	if e.nodes.Len() < NodesLengthPerEntry {
		return
	}
	if e.lastGCTime.Add(EntryGCInterval).Before(time.Now()) {
		return
	}
	e.lastGCTime = time.Now()
	nodes := new(Nodes)
	for _, t := range *(e.nodes) {
		if t.lastUsed.Add(TopicMaxIdleTime).Before(time.Now()) {
			continue
		}
		heap.Push(nodes, t)
	}
	copy((*e.nodes)[:], (*nodes)[:])
	nodes = new(Nodes)
	if e.nodes.Len() < NodesLengthPerEntry {
		for _, t := range *(e.replacementes) {
			if t.lastUsed.Add(TopicMaxIdleTime).Before(time.Now()) {
				continue
			}
			if e.nodes.Len() < NodesLengthPerEntry {
				heap.Push(e.nodes, t)
				continue
			}
			heap.Push(nodes, t)
		}
		e.replacementes = nodes
	}
}

func distcmp(target, a, b Topic) int {
	for i := range target {
		da := a[i] ^ target[i]
		db := b[i] ^ target[i]
		if da > db {
			return 1
		} else if da < db {
			return -1
		}
	}
	return 0
}

type disCalactor struct {
	entries []*Node
	target  Topic
}

func (d *disCalactor) push(n *Node, maxElems int) {
	ix := sort.Search(len(d.entries), func(i int) bool {
		return distcmp(d.target, d.entries[i].topic, n.topic) > 0
	})
	if len(d.entries) < maxElems {
		d.entries = append(d.entries, n)
	}
	if ix < len(d.entries) {
		copy(d.entries[ix+1:], d.entries[ix:])
		d.entries[ix] = n
	}
}

```


