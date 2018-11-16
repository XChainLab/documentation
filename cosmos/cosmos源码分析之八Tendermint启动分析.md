# cosmos源码分析之八Tendermint启动分析

## 一、启动流程介绍
Tendermint的启动流程比较简单，可能跟它没有相关的业务场景有关系，大体分为三步：第一步配置命令选项；第二步启动并运行节点；第三步，启动相关命令。代码上看上去也要比以太坊等其它链的启动代码更简洁。
</br>
这里需要说明的是，它用的命令行工具是cobra这个第三方的工具，不是以太坊等用的cli。

## 二、入口
先看一下入口的函数：
</br>

``` golang
func main() {
	rootCmd := cmd.RootCmd
	rootCmd.AddCommand(
		cmd.GenValidatorCmd,
		cmd.InitFilesCmd,
		cmd.ProbeUpnpCmd,
		cmd.LiteCmd,
		cmd.ReplayCmd,
		cmd.ReplayConsoleCmd,
		cmd.ResetAllCmd,
		cmd.ResetPrivValidatorCmd,
		cmd.ShowValidatorCmd,
		cmd.TestnetFilesCmd,
		cmd.ShowNodeIDCmd,
		cmd.GenNodeKeyCmd,
		cmd.VersionCmd)

	// NOTE:
	// Users wishing to:
	//	* Use an external signer for their validators
	//	* Supply an in-proc abci app
	//	* Supply a genesis doc file from another source
	//	* Provide their own DB implementation
	// can copy this file and use something other than the
	// DefaultNewNode function
	nodeFunc := nm.DefaultNewNode

	// Create & start node
	rootCmd.AddCommand(cmd.NewRunNodeCmd(nodeFunc))

	cmd := cli.PrepareBaseCmd(rootCmd, "TM", os.ExpandEnv(filepath.Join("$HOME", cfg.DefaultTendermintDir)))
	if err := cmd.Execute(); err != nil {
		panic(err)
	}
}
```
</br>
是不是非常简单。它的根命令操作如下：
</br>

``` golang
// RootCmd is the root command for Tendermint core.
var RootCmd = &cobra.Command{
	Use:   "tendermint",
	Short: "Tendermint Core (BFT Consensus) in Go",
	PersistentPreRunE: func(cmd *cobra.Command, args []string) (err error) {
		if cmd.Name() == VersionCmd.Name() {
			return nil
		}
		config, err = ParseConfig()
    ......
		logger = logger.With("module", "main")
		return nil
	},
}
```
</br>
在上面的代码中，会调用cmd.NewRunNodeCmd(nodeFunc)，而在它上面一行代码nodeFunc := nm.DefaultNewNode已经创建了运行参数，这个函数的目的其实很简单，创建Node并启动，同时开始监听，看一下它的代码（cmd/tendermint/commands/run_node.go）:
</br>

``` golang
// NewRunNodeCmd returns the command that allows the CLI to start a node.
// It can be used with a custom PrivValidator and in-process ABCI application.
func NewRunNodeCmd(nodeProvider nm.NodeProvider) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "node",
		Short: "Run the tendermint node",
		RunE: func(cmd *cobra.Command, args []string) error {
			// Create & start node
			n, err := nodeProvider(config, logger)
			if err != nil {
				return fmt.Errorf("Failed to create node: %v", err)
			}

			if err := n.Start(); err != nil {
				return fmt.Errorf("Failed to start node: %v", err)
			}
			logger.Info("Started node", "nodeInfo", n.Switch().NodeInfo())

			// Trap signal, run forever.
			n.RunForever()

			return nil
		},
	}

	AddNodeFlags(cmd)
	return cmd
}
```
</br>
其时它就是利用了Node节点的默认的创建函数传送到Cmd中进行节点的创建，创建完成后使用Start函数将其启动。在最后使用节点的信号监听函数来处理相关的消息。

## 三、创建NODE
在上面的分析知道，命令运行开始创建Node，先看一下Node的数据结构：
</br>

``` golang
type Node struct {
	cmn.BaseService

	// config
	config        *cfg.Config
	genesisDoc    *types.GenesisDoc   // initial validator set
	privValidator types.PrivValidator // local node's validator key

	// network
	sw       *p2p.Switch  // p2p connections
	addrBook pex.AddrBook // known peers

	// services
	eventBus         *types.EventBus // pub/sub for services
	stateDB          dbm.DB
	blockStore       *bc.BlockStore         // store the blockchain to disk
	bcReactor        *bc.BlockchainReactor  // for fast-syncing
	mempoolReactor   *mempl.MempoolReactor  // for gossipping transactions
	consensusState   *cs.ConsensusState     // latest consensus state
	consensusReactor *cs.ConsensusReactor   // for participating in the consensus
	evidencePool     *evidence.EvidencePool // tracking evidence
	proxyApp         proxy.AppConns         // connection to the application
	rpcListeners     []net.Listener         // rpc servers
	txIndexer        txindex.TxIndexer
	indexerService   *txindex.IndexerService
}
```
</br>
看一下上面的调用的创建Node的函数：
</br>

``` golang
// DefaultNewNode returns a Tendermint node with default settings for the
// PrivValidator, ClientCreator, GenesisDoc, and DBProvider.
// It implements NodeProvider.
func DefaultNewNode(config *cfg.Config, logger log.Logger) (*Node, error) {
	return NewNode(config,
		pvm.LoadOrGenFilePV(config.PrivValidatorFile()),
		proxy.DefaultClientCreator(config.ProxyApp, config.ABCI, config.DBDir()),
		DefaultGenesisDocProviderFunc(config),
		DefaultDBProvider,
		logger,
	)
}
```
</br>
NewNode这个函数太长了，这里节选一下：
</br>

``` golang
// NewNode returns a new, ready to go, Tendermint Node.
func NewNode(config *cfg.Config,
	privValidator types.PrivValidator,
	clientCreator proxy.ClientCreator,
	genesisDocProvider GenesisDocProvider,
	dbProvider DBProvider,
	logger log.Logger) (*Node, error) {

	// Get BlockStore
	blockStoreDB, err := dbProvider(&DBContext{"blockstore", config})
	if err != nil {
		return nil, err
	}
	blockStore := bc.NewBlockStore(blockStoreDB)

	// Get State
	stateDB, err := dbProvider(&DBContext{"state", config})
	if err != nil {
		return nil, err
	}
......

	// Make MempoolReactor
	mempoolLogger := logger.With("module", "mempool")
	mempool := mempl.NewMempool(config.Mempool, proxyApp.Mempool(), state.LastBlockHeight)
	mempool.InitWAL() // no need to have the mempool wal during tests
	mempool.SetLogger(mempoolLogger)
	mempoolReactor := mempl.NewMempoolReactor(config.Mempool, mempool)
	mempoolReactor.SetLogger(mempoolLogger)

	if config.Consensus.WaitForTxs() {
		mempool.EnableTxsAvailable()
	}

	// Make Evidence Reactor
	evidenceDB, err := dbProvider(&DBContext{"evidence", config})
	if err != nil {
		return nil, err
	}
	evidenceLogger := logger.With("module", "evidence")
	evidenceStore := evidence.NewEvidenceStore(evidenceDB)
	evidencePool := evidence.NewEvidencePool(stateDB, evidenceStore)
	evidencePool.SetLogger(evidenceLogger)
	evidenceReactor := evidence.NewEvidenceReactor(evidencePool)
	evidenceReactor.SetLogger(evidenceLogger)

	blockExecLogger := logger.With("module", "state")
	// make block executor for consensus and blockchain reactors to execute blocks
	blockExec := sm.NewBlockExecutor(stateDB, blockExecLogger, proxyApp.Consensus(), mempool, evidencePool)

	// Make BlockchainReactor
	bcReactor := bc.NewBlockchainReactor(state.Copy(), blockExec, blockStore, fastSync)
	bcReactor.SetLogger(logger.With("module", "blockchain"))

	// Make ConsensusReactor
	consensusState := cs.NewConsensusState(config.Consensus, state.Copy(),
		blockExec, blockStore, mempool, evidencePool)
	consensusState.SetLogger(consensusLogger)
	if privValidator != nil {
		consensusState.SetPrivValidator(privValidator)
	}
	consensusReactor := cs.NewConsensusReactor(consensusState, fastSync)
	consensusReactor.SetLogger(consensusLogger)

	p2pLogger := logger.With("module", "p2p")

	sw := p2p.NewSwitch(config.P2P)
......
	addrBook := pex.NewAddrBook(config.P2P.AddrBookFile(), config.P2P.AddrBookStrict)
.......

	eventBus := types.NewEventBus()
	eventBus.SetLogger(logger.With("module", "events"))

	// services which will be publishing and/or subscribing for messages (events)
	// consensusReactor will set it on consensusState and blockExecutor
	consensusReactor.SetEventBus(eventBus)

......

	node := &Node{
		config:        config,
		genesisDoc:    genDoc,
		privValidator: privValidator,

		sw:       sw,
		addrBook: addrBook,

		stateDB:          stateDB,
		blockStore:       blockStore,
		bcReactor:        bcReactor,
		mempoolReactor:   mempoolReactor,
		consensusState:   consensusState,
		consensusReactor: consensusReactor,
		evidencePool:     evidencePool,
		proxyApp:         proxyApp,
		txIndexer:        txIndexer,
		indexerService:   indexerService,
		eventBus:         eventBus,
	}
	node.BaseService = *cmn.NewBaseService(logger, "Node", node)
	return node, nil
}
```
</br>
启动的Start函数会调用Node.go中的OnStart函数来实现Node的启动：
</br>

``` golang
// OnStart starts the Node. It implements cmn.Service.
func (n *Node) OnStart() error {
	err := n.eventBus.Start()
	if err != nil {
		return err
	}

	// Create & add listener
	protocol, address := cmn.ProtocolAndAddress(n.config.P2P.ListenAddress)
	l := p2p.NewDefaultListener(protocol, address, n.config.P2P.SkipUPNP, n.Logger.With("module", "p2p"))
	n.sw.AddListener(l)

	// Generate node PrivKey
	// TODO: pass in like privValidator
	nodeKey, err := p2p.LoadOrGenNodeKey(n.config.NodeKeyFile())
	if err != nil {
		return err
	}
	n.Logger.Info("P2P Node ID", "ID", nodeKey.ID(), "file", n.config.NodeKeyFile())

	nodeInfo := n.makeNodeInfo(nodeKey.ID())
	n.sw.SetNodeInfo(nodeInfo)
	n.sw.SetNodeKey(nodeKey)

	// Add ourselves to addrbook to prevent dialing ourselves
	n.addrBook.AddOurAddress(nodeInfo.NetAddress())

	// Start the RPC server before the P2P server
	// so we can eg. receive txs for the first block
	if n.config.RPC.ListenAddress != "" {
		listeners, err := n.startRPC()
		if err != nil {
			return err
		}
		n.rpcListeners = listeners
	}

	// Start the switch (the P2P server).
	err = n.sw.Start()
	if err != nil {
		return err
	}

	// Always connect to persistent peers
	if n.config.P2P.PersistentPeers != "" {
		err = n.sw.DialPeersAsync(n.addrBook, cmn.SplitAndTrim(n.config.P2P.PersistentPeers, ",", " "), true)
		if err != nil {
			return err
		}
	}

	// start tx indexer
	return n.indexerService.Start()
}
```
</br>
需要说明的是，这个Start函数位于"github.com/tendermint/tmlibs/common"中的server.go中。有一个好的IDE，同时网络好能自动下载相关的包真是太羡慕了。
</br>
同样，启动监听信号的函数也是在上面的库中，即：
</br>

``` golang
// RunForever waits for an interrupt signal and stops the node.
func (n *Node) RunForever() {
	// Sleep forever and then...
  //下面这个信号处理
	cmn.TrapSignal(func() {
		n.Stop()
	})
}
```
</br>
节点的停止就要被它监控：
</br>

``` golang
func (n *Node) OnStop() {
	n.BaseService.OnStop()

	n.Logger.Info("Stopping Node")
	// TODO: gracefully disconnect from peers.
	n.sw.Stop()

	for _, l := range n.rpcListeners {
		n.Logger.Info("Closing rpc listener", "listener", l)
		if err := l.Close(); err != nil {
			n.Logger.Error("Error closing listener", "listener", l, "err", err)
		}
	}

	n.eventBus.Stop()
	n.indexerService.Stop()

	if pvsc, ok := n.privValidator.(*pvm.SocketPV); ok {
		if err := pvsc.Stop(); err != nil {
			n.Logger.Error("Error stopping priv validator socket client", "err", err)
		}
	}
}
```
</br>
节点启动停止可以进行控制后，就可以进行在节点上的各种动作了，如共识、通信等。
</br>

## 四、网络通信
网络通信的启停就在上面的OnStart函数中，分成了两部分，服务监听和拨号，在服务监听中首先注册P2P的协议，这个和以太坊类似，然后创建监听器并添加到相关的节点中。看下面的代码：
</br>

``` golang
// skipUPNP: If true, does not try getUPNPExternalAddress()
func NewDefaultListener(protocol string, lAddr string, skipUPNP bool, logger log.Logger) Listener {
	// Local listen IP & port
	lAddrIP, lAddrPort := splitHostPort(lAddr)

	// Create listener
	var listener net.Listener
	var err error
	for i := 0; i < tryListenSeconds; i++ {
		listener, err = net.Listen(protocol, lAddr)
		if err == nil {
			break
		} else if i < tryListenSeconds-1 {
			time.Sleep(time.Second * 1)
		}
	}
	if err != nil {
		panic(err)
	}
	// Actual listener local IP & port
	listenerIP, listenerPort := splitHostPort(listener.Addr().String())
	logger.Info("Local listener", "ip", listenerIP, "port", listenerPort)

	// Determine internal address...
	var intAddr *NetAddress
	intAddr, err = NewNetAddressStringWithOptionalID(lAddr)
	if err != nil {
		panic(err)
	}

	// Determine external address...
	var extAddr *NetAddress
	if !skipUPNP {
		// If the lAddrIP is INADDR_ANY, try UPnP
		if lAddrIP == "" || lAddrIP == "0.0.0.0" {
			extAddr = getUPNPExternalAddress(lAddrPort, listenerPort, logger)
		}
	}
	// Otherwise just use the local address...
	if extAddr == nil {
		extAddr = getNaiveExternalAddress(listenerPort, false, logger)
	}
	if extAddr == nil {
		panic("Could not determine external address!")
	}

	dl := &DefaultListener{
		listener:    listener,
		intAddr:     intAddr,
		extAddr:     extAddr,
		connections: make(chan net.Conn, numBufferedConnections),
	}
	dl.BaseService = *cmn.NewBaseService(logger, "DefaultListener", dl)
	err = dl.Start() // Started upon construction
	if err != nil {
		logger.Error("Error starting base service", "err", err)
	}
	return dl
}
func (l *DefaultListener) OnStart() error {
	if err := l.BaseService.OnStart(); err != nil {
		return err
	}
	go l.listenRoutine()
	return nil
}

func (l *DefaultListener) OnStop() {
	l.BaseService.OnStop()
	l.listener.Close() // nolint: errcheck
}
```
</br>
同上面一样，会启动这个监听，前面省略了RPC的启动。这个没有啥特殊之处。
</br>
有了服务，然后再启动连接：
</br>

``` golang
func (sw *Switch) DialPeersAsync(addrBook AddrBook, peers []string, persistent bool) error {
	netAddrs, errs := NewNetAddressStrings(peers)
	// only log errors, dial correct addresses
	for _, err := range errs {
		sw.Logger.Error("Error in peer's address", "err", err)
	}

	ourAddr := sw.nodeInfo.NetAddress()

	// TODO: this code feels like it's in the wrong place.
	// The integration tests depend on the addrBook being saved
	// right away but maybe we can change that. Recall that
	// the addrBook is only written to disk every 2min
	if addrBook != nil {
		// add peers to `addrBook`
		for _, netAddr := range netAddrs {
			// do not add our address or ID
			if !netAddr.Same(ourAddr) {
				if err := addrBook.AddAddress(netAddr, ourAddr); err != nil {
					sw.Logger.Error("Can't add peer's address to addrbook", "err", err)
				}
			}
		}
		// Persist some peers to disk right away.
		// NOTE: integration tests depend on this
		addrBook.Save()
	}

	// permute the list, dial them in random order.
	perm := sw.rng.Perm(len(netAddrs))
	for i := 0; i < len(perm); i++ {
		go func(i int) {
			j := perm[i]

			addr := netAddrs[j]
			// do not dial ourselves
			if addr.Same(ourAddr) {
				return
			}

......
		}(i)
	}
	return nil
}

```
</br>

## 五、共识
网络启动后，共识启动的时机也就成熟了，毕竟共识是需要在多节点间进行通信的，P2P不起来，共识也没法完成工作，那么共识在哪里开始启动的呢？
</br>
在创建Node的函数NewNode中，会创建共识的反应器NewConsensusReactor，并将其添加eventBus中。同样也会在NewNode中进行NewConsensusState，这样在启动节点时会调用总线事件启动：
</br>

``` golang
func (conR *ConsensusReactor) OnStart() error {
	conR.Logger.Info("ConsensusReactor ", "fastSync", conR.FastSync())
	if err := conR.BaseReactor.OnStart(); err != nil {
		return err
	}

	conR.subscribeToBroadcastEvents()

	if !conR.FastSync() {
		err := conR.conS.Start()
		if err != nil {
			return err
		}
	}

	return nil
}

// OnStart implements cmn.Service.
// It loads the latest state via the WAL, and starts the timeout and receive routines.
func (cs *ConsensusState) OnStart() error {
	if err := cs.evsw.Start(); err != nil {
		return err
	}

	// we may set the WAL in testing before calling Start,
	// so only OpenWAL if its still the nilWAL
	if _, ok := cs.wal.(nilWAL); ok {
		walFile := cs.config.WalFile()
		wal, err := cs.OpenWAL(walFile)
		if err != nil {
			cs.Logger.Error("Error loading ConsensusState wal", "err", err.Error())
			return err
		}
		cs.wal = wal
	}

	// we need the timeoutRoutine for replay so
	// we don't block on the tick chan.
	// NOTE: we will get a build up of garbage go routines
	// firing on the tockChan until the receiveRoutine is started
	// to deal with them (by that point, at most one will be valid)
	if err := cs.timeoutTicker.Start(); err != nil {
		return err
	}

	// we may have lost some votes if the process crashed
	// reload from consensus log to catchup
	if cs.doWALCatchup {
		if err := cs.catchupReplay(cs.Height); err != nil {
			cs.Logger.Error("Error on catchup replay. Proceeding to start ConsensusState anyway", "err", err.Error())
			// NOTE: if we ever do return an error here,
			// make sure to stop the timeoutTicker
		}
	}

	// now start the receiveRoutine
	go cs.receiveRoutine(0)

	// schedule the first round!
	// use GetRoundState so we don't race the receiveRoutine for access
	cs.scheduleRound0(cs.GetRoundState())

	return nil
}
```
</br>
再下来，就是共识的过程了，这个在前面的分析里简单的说明一下，这个共识的过程其实没有什么太复杂之处，看代码结合着Tendermint的文档即可。
</br>

## 六、总结
通过上面的代码的简单分析，基本了解了整个Tendermint的启动流程，其实诸如IBC通信等这里都没有深入展开介绍，如果有兴趣可以去GITHUB上下来源码认真的比对着相关文档看看。
</br>
正如Tendermint的分而治之的思想一样，一个模块一个模块的分析Tendermint，其实也没有什么特别的难点。
</br>
