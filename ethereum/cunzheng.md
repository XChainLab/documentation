# 基于以太坊区块链的电子存证应用

## 一、电子存证技术概述

传统的电子存证简单来说就是将源信息经过加密存储在一个具有公信力的独立第三方处，并绑定时间戳、创建人等信息用来证明在某个时间点存在这样的信息。举例来说，对于原创作品的保护，作者可以在创作完成后第一时间进行电子存证，以保证在以后出现侵权后证明自己最早创作了作品从而保护自己的权益。

电子存证的源信息可以是一段文本，文档，图片，视频等形式。对于这种各式各样的形式，电子存证一般存储的是源信息的哈希摘要；哈希是一段定长的比特串，类似于源信息的指纹，源信息只要改变，哈希就会和原来的完全不一样，由于哈希基本上是不可遍历的，所以在现实中可以认为哈希和源信息一一对应。哈希的这种特性普遍应用在文件指纹等场景，例如下载文件中的哈希校验。电子存证存储的哈希值是可以证明源信息真实未经篡改。哈希的另一个特性是无法从哈希摘要反推出原始信息，所以这样也保证了一些敏感信息的隐私性。

## 二、区块链电子存证的优势

对于传统的电子存证，具有公信力的独立第三方是一个很重要的角色；需要存证、取证、验证的各方都无条件信任。这样的第三方权限过于集中，如果第三方恶意修改数据，则基本无从查证；所以这样的第三方只能通过非技术的其他手段保证不去作恶。而区块链本身通过一环套一环的链式结构、分布式的存储、分布式的共识机制将这样过大的权利分散到所有参与者身上，保证了不产生这样一个权限过大的中心化第三方来具有作恶的可能。

通过区块链解决的存证中的信任问题，基于这样的一个前提，我们设计了基于以太坊的电子存证应用。

## 三、区块链存证合约设计

区块链上的数据经过矿工打包进区块中后基本上不可能更改，所以存证合约设计时候只需要做简单的读写操作。我们设计的存证合约读写的数据结构为：

```solidity
struct Abstract {
    uint timestamp;
    address sender;
    uint version;
    bytes32 hash;
    byte[512] extend;
}
```

数据结构中包含时间戳，调用存证合约的地址、存证的哈希值、扩展字段和标识版本的 version 字段。扩展字段和版本由使用方自定义编码和解码方式。通过这样的数据结构，构造一个 `mapping(bytes32 => Abstract)` Map 来用于分别保存存证信息，Map 结构的 Key 可以简单设置为存证的哈希值或者其他可追溯的值。

在这样结构上再封装对 Map 的读写操作就是一个简单的存证合约。可是由于区块链的特性，合约一旦上链后就不能更改了，所以如果合约逻辑出现漏洞就影响比较大，并且不能修复，重新部署合约又会丢失原有的数据，这样设计的合约是不可维护的。所以设计对这样的合约进行更改，将使用方直接调用 Map 操作的读写进行切断，在中间加入一个访问控制的合约层，这样经过修改的合约结构如下：

**底层数据层合约**：仅封装对 Map 结构的读写操作，不设计具体的业务逻辑；在合约层加入权限控制，维护访问地址的白名单，仅白名单内部的地址具有操作合约数据的权限；仅合约部署者具有控制白名单的权限。

**上层逻辑合约**：封装了简单的存证业务逻辑，上层逻辑没有数据存储操作，在合约部署时候传入底层合约的地址作为参数，数据存储通过合约调用底层合约来实现。

这样分层后，一旦上层逻辑出现问题，可以通过管理员吊销上层合约的读写访问权限来阻止进一步的损失；合约升级是通过部署新的上层合约，赋予新的上层合约权限，吊销旧上层合约权限来实现；底层合约出现问题，也可以通过升级上层合约，在逻辑上绕过。

具体底层合约的代码如下：

```solidity
pragma solidity ^0.4.17;

contract DataModel {
    struct Abstract {
        uint timestamp;
        address sender;
        uint version;
        bytes32 hash;
        byte[512] extend;
    }

    mapping(bytes32 => Abstract) abstractData;
    mapping(address => bool) public allowedMap;
    address[] public allowedArray;

    event AddressAllowed(address _handler, address _address);
    event AddressDenied(address _handler, address _address);
    event DataSaved(address indexed _handler, uint timestamp, address indexed sender, uint version, bytes32 hash);
    event ExtendSaved(address indexed _handler, byte[512] extend);
    event ExtendNotSave(address indexed _handler, uint version, byte[512] extend);

    function DataModel() public {
        allowedMap[msg.sender] = true;
        allowedArray.push(msg.sender);
    }

    modifier allow() {
        require(allowedMap[msg.sender] == true);
        _;
    }

    function allowAccess(address _address) allow public {
        allowedMap[_address] = true;
        allowedArray.push(_address);
        AddressAllowed(msg.sender, _address);
    }

    function denyAccess(address _address) allow public {
        allowedMap[_address] = false;
        AddressDenied(msg.sender, _address);
    }

    function getData(bytes32 _key) public view returns(uint, address, uint, bytes32, byte[512]) {
        return (
            abstractData[_key].timestamp,
            abstractData[_key].sender,
            abstractData[_key].version,
            abstractData[_key].hash,
            abstractData[_key].extend
        );
    }

    function setData(bytes32 _key, uint timestamp, address sender, uint version, bytes32 hash) allow public {
        abstractData[_key].timestamp = timestamp;
        abstractData[_key].sender = sender;
        abstractData[_key].version = version;
        abstractData[_key].hash = hash;
        DataSaved(msg.sender, timestamp, sender, version, hash);
    }

    function setExtend(bytes32 _key, byte[512] extend) allow public {
        if (abstractData[_key].version > 0) {
            for (uint256 i; i < 512; i++) {
                abstractData[_key].extend[i] = extend[i];
            }
            ExtendSaved(msg.sender, extend);
        } else {
            ExtendNotSave(msg.sender, abstractData[_key].version, extend);
        }
    }
}
```

上层合约的代码如下：

```solidity
pragma solidity ^0.4.20;

import "./data-model.sol";

contract Storage {
    DataModel dataModel;
    uint currentVersion = 1;

    event StorageSaved(address handler, bytes32 indexed hashKey, uint timestamp, uint version, byte[512] extend);

    function Storage(address dataModelAddress) public {
        dataModel = DataModel(dataModelAddress);
        // require(dataModelAddress.delegatecall(bytes4(keccak256("allowAccess(address)")), this));
    }

    function getData(bytes32 key) public view returns(uint timestamp, address sender, uint version, bytes32 hashKey, string extend) {
        byte[512] memory extendByte;

        (timestamp, sender, version, hashKey, extendByte) = dataModel.getData(key);

        bytes memory bytesArray = new bytes(512);
        for (uint256 i; i < 512; i++) {
            bytesArray[i] = extendByte[i];
        }

        extend = string(bytesArray);
        return(timestamp, sender, version, hashKey, extend);
    }

    function saveData(bytes32 hashKey, byte[512] extend) public {
        dataModel.setData(hashKey, block.timestamp, msg.sender, currentVersion, hashKey);
        dataModel.setExtend(hashKey, extend);

        StorageSaved(msg.sender, hashKey, block.timestamp, currentVersion, extend);
    }
}
```

### 四、存证应用和以太坊区块链的交互

我们存证应用采用的是 Go 语言开发，通过 RPC 调用和链进行交互；由于采用 Go 语言开发，而正好以太坊官方提供 `go-ethereum` 的开源代码，所以以太坊 SDK 这块就直接选用这份开源代码；代码中不仅有主动调用 RPC 接口，而且需要接收节点推送的合约事件，所以 RPC 调用基于的是 WebSocket 协议，需要节点开启 WebSocket RPC 调用支持，可以通过启动参数 `--ws --wsaddr value --wsport value --wsapi value` 来实现[WIKI](https://github.com/ethereum/go-ethereum/wiki/Command-Line-Options)，或者通过 JavaScript Console 的 [Admin API](https://github.com/ethereum/go-ethereum/wiki/Management-APIs#admin_startws)来开启。

调用 Go SDK 的基本流程如下（代码省略错误处理等逻辑，仅保留核心流程）：

```go
import (
	"github.com/ethereum/go-ethereum/ethclient"
    "github.com/ethereum/go-ethereum/rpc"
    "github.com/ethereum/go-ethereum/accounts/abi"
	"github.com/ethereum/go-ethereum/accounts/abi/bind"
	"github.com/ethereum/go-ethereum/accounts/keystore"
	"github.com/ethereum/go-ethereum/common"
	"github.com/ethereum/go-ethereum/core/types"
)

// 初始化 RPC 连接
RPCClient, _ := rpc.Dial(conf.BlockChainConf.RPCUrl)

// 初始化 ethclient
cli := ethclient.NewClient(RPCClient)

// 导入 ABI 接口字符串
parsedABI, _ := abi.JSON(strings.NewReader(evidenceABI))

// 初始化合约实例
evidence := bind.NewBoundContract(conf.BlockChainConf.ContractAddress, parsedABI, cli, cli, nil)

// 初始化上下文
ctx, cancel := context.WithTimeout(context.Background(), conf.BlockChainConf.ConnTimeout)
defer cancel()

// 交易签名私钥
auth := bind.NewKeyedTransactor(account.PrivateKey)
auth.Context = ctx

// 调用 RPC 发送存证合约交易
tx, _ := evidence.Transact(auth, "saveData", hash, stringToBytes512(extend))
```

最终返回的 tx 则为交易信息，这时候交易并没有即时出块，需要等待出块节点出块；这里通过监听合约的日志事件来实现：

```go
// 订阅事件的过滤条件，这里传入合约的地址
query := ethereum.FilterQuery{
    Addresses: []common.Address{conf.BlockChainConf.ContractAddress},
}

// Log 通道接收
var logChan = make(chan types.Log)
ctx := context.Background()

// 初始化客户端
client, _ := blockchain.InitClient()

// 初始化事件监听
subscribe, _ := client.SubscribeFilterLogs(ctx, query, logChan)

// 同样解析出 ABI 合约接口
parsedABI, _ := abi.JSON(strings.NewReader(evidenceABI))

// 收到的事件结构，和合约代码中数据结构对应
var receivedData struct {
    Handler   common.Address
    HashKey   common.Hash
    Timestamp *big.Int
    Version   *big.Int
    Extend    Bytes512
}

for {
    select {
    case err := <-evt.Subscribe.Err():
        fmt.Printf("receive Error: %s\n", err.Error())
    case log := <-LogChan:
        // 解包收到的 Log，receivedData 则为接收事件的数据
	    err := parsedABI.Unpack(&receivedData, "StorageSaved", log.Data)
    }
}
```

通过这样子，就可以在区块链出块后接受到事件，保证合约方法的成功调用

取证一种方式是通过调用合约的 `getData` 方法来做，和写入存证数据代码大同小异，如下：

```go
// 对应存证的 evidence.Transact 方法
err = evidence.Call(callOpts, &output, "getData", key)
```

另一种方式是通过合约的 Log 过滤来实现，如下：

```go
// 这里过滤条件选用合约中 Map 数据的 Key
query := ethereum.FilterQuery{
    Topics: [][]common.Hash{[]common.Hash{}, []common.Hash{hashKey}},
}

// 调用 Client 的 FilterLogs 方法
logs, err := client.FilterLogs(ctx, query)

// 接着类似于监听事件那里，解包收到的 Log 得到数据
```

### 五、结语

存证和区块链结合是一个和合适透明的场景，利用区块链解决的存证中存在的第三方信任问题；可是司法并没有跟上技术进步的节奏；存证现在还处于技术实现阶段，距离真正落地使用应该还有一段距离，这些都需要我们时刻关注相关信息。
