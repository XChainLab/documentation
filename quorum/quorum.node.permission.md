# J.P.Morgan Quorum 节点授权管理

## 简介

Quorum的网络节点授权，是用来控制哪些节点可以连接到指定节点、以及可以从哪些指定节点移除的功能。目前，当启动geth节点时，通过加入--permissioned命令行参数在节点级别处进行管理。

如果设置了--permissioned参数，节点将查找名为<data-dir>/permissioned-nodes.json的文件。此文件包含此节点可以连接并接受来自其连接的enodes白名单。因此，启用权限后，只有permissioned-nodes.json文件中列出的节点成为网络的一部分。 如果指定了--permissioned参数，但没有节点添加到permissioned-nodes.json文件，则该节点既不能连接到任何节点也不能接受任何接入的连接。

如果设置了--permissioned参数，但permissioned-nodes.json文件为空或者仅存在于节点的<data-dir>文件夹中，则该节点将启动，但它不会连接到任何其他节点，也不会接受来自其他节点的任何接入连接请求。无论是哪种情况，都期望看到错误记录。

permissioned-nodes.json文件包含一个节点参数列表（enode://nodeid@ip:port），指定该特定节点将接受来自连接的接入连接并进行主动拨出连接。

permissioned-nodes.json格式如下：

 ["enode://nodeid1@ip1:port1", "enode://nodeid2@ip2:port2", "enode://nodeid3@ip3:port3", ]
例如：（便于查看，节点id仅截取部分展示）

["enode://8475a01f62a1948126dc1f0d22ecaaaf77e[::]:30301", "enode://c5660501f496360e49ded734a889c98b7da[::]:30302","enode://84bd7df4bda71fb90493cf4706455335919[::]:30303"]
以上将确保此节点只能接受来自/到达此白名单中3个节点的接入或接出连接。


geth选项列表下，--permissioned参数可用：

$ geth --help
QUORUM OPTIONS:
  --permissioned  If enabled, the node will allow only a defined list of nodes to connect


添加新节点：

任何添加到permissioned-nodes.json文件的内容，都将在后续发出接入或接出请求时，被服务器动态获取。节点不需要重新启动以便更改生效。

删除现有节点：

从permissioned-nodes.json文件中删除现有的连接节点，不会立即删除那些现有的连接节点。但是，如果连接由于任何原因而被断开，并且随后的连接请求将从被删除的节点id中产生，它将作为新请求的一部分被拒绝。


## 源代码解读

在Server struct这个结构体中，添加了EnableNodePermission字段，用来标识是否开启了网络节点的权限管理。实际上这个标识就是在启动geth命令的时候，如果在命令行传递了--permissioned参数，则这个标识为true，否则就是false。

```go
// quorum/cmd/utils/flags.go
// 这里展示了对命令行参数的定义
var (
  // Quorum
  EnableNodePermissionFlag = cli.BoolFlag{
    Name:  "permissioned",
    Usage: "If enabled, the node will allow only a defined list of nodes to connect",
  }
)

// quorum/cmd/utils/flags.go
// 这里是解析命令行参数
// SetNodeConfig applies node-related command line flags to the config.
func SetNodeConfig(ctx *cli.Context, cfg *node.Config) {
  cfg.EnableNodePermission = ctx.GlobalBool(EnableNodePermissionFlag.Name)
}
```

Server.SetupConn 这个函数是在网络链接的过程中，执行握手协议，并且尝试添加这个网络链接作为一个peer。在这个函数中，在设置connection的时候，去判断是否启动了节点授权，如果启动了，就去读取相应的节点授权列表

```go
// quorum/p2p/server.go
func (srv *Server) SetupConn(fd net.Conn, flags connFlag, dialDest *discover.Node) {
  if srv.EnableNodePermission {
		log.Trace("Node Permissioning is Enabled.")
		node := c.id.String()
		direction := "INCOMING"
		if dialDest != nil {
			node = dialDest.ID.String()
			direction = "OUTGOING"
			log.Trace("Node Permissioning", "Connection Direction", direction)
		}

		if !isNodePermissioned(node, currentNode, srv.DataDir, direction) {
			return
		}
	}
}
```

在判断一个节点是不是授权节点的时候，就用到了授权节点的配置文件，下面是读配置文件并且判断节点的代码。

```go
// quorum/p2p/permissions.go
// check if a given node is permissioned to connect to the change
// 这里是判断一个指定的节点是否被授权加入到这个网络
func isNodePermissioned(nodename string, currentNode string, datadir string, direction string) bool {

	var permissionedList []string
	nodes := parsePermissionedNodes(datadir)
	for _, v := range nodes {
		permissionedList = append(permissionedList, v.ID.String())
	}

  for _, v := range permissionedList {
		if v == nodename {
			return true
		}
	}
	return false
}

// quorum/p2p/permissions.go
// 这里就是去读取permissioned-nodes.json配置文件
func parsePermissionedNodes(DataDir string) []*discover.Node {

	path := filepath.Join(DataDir, PERMISSIONED_CONFIG)
	// Load the nodes from the config file
	blob, err := ioutil.ReadFile(path)

	nodelist := []string{}
	if err := json.Unmarshal(blob, &nodelist); err != nil {
		return nil
	}
	// Interpret the list as a discovery node array
	var nodes []*discover.Node
	for _, url := range nodelist {
		nodes = append(nodes, node)
	}
	return nodes
}
```


判断一个节点是不是授权节点的时机，无非就是两个，第一个时机是主动去链接另外一个节点的时候，另外一个时机就是被动的接受另外一个节点的链接，在这两个时间点都做好判断，就可以控制住节点授权的问题，把非授权节点挡在大门外。下面的代码就展示了这两个时间点的操作。

```go
// quorum/p2p/dial.go
// dial 函数就是主动的去链接另外一个节点
func (t *dialTask) dial(srv *Server, dest *discover.Node) bool {
	fd, err := srv.Dialer.Dial(dest)
	mfd := newMeteredConn(fd, false)
	srv.SetupConn(mfd, t.flags, dest)
	return true
}

// quorum/p2p/dial.go
// 在这里就是监听其他节点的链接请求，收到请求之后，就去验证节点是否被授权
func (srv *Server) listenLoop() {
  go func() {
    srv.SetupConn(fd, inboundConn, nil)
    slots <- struct{}{}
  }()
}
```
