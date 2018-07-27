# 让你的区块链兼容以太坊智能合约
## 引言
随着区块链技术以及应用的普及，越来越多的区块链出现在大众视野中。由于区块链技术的开源特性，任何公司和个人都可以方便快捷的获取最新的区块链核心技术，通过对这些技术的选择和整合，最后开发和搭建满足特定业务需求的区块链产品。以太坊作为目前区块链2.0的杰出代表被作为诸多区块链项目开发的基础，甚至有人统计100个区块链项目中有94个是基于以太坊，而以太坊社区更是有25万的开发者在活跃着，因此以太坊成为大家争相研究和进行区块链开发的典型。EVM作为以太坊中重要的组件，其运行着以太坊上至关重要的智能合约，由于以太坊庞大的社区和经济环境，作为一个新出现的区块链兼容以太坊的智能合约逐渐的变为一种显性的需求，本文将介绍一个区块链兼容以太坊智能合约的思路和具体的实现。
## 实现思路
以太坊虚拟机作为一个图灵完备的虚拟机有其独特的优势和特点，这些在公众号之前的文章有所介绍。运行在以太坊上的智能合约实现了以太坊上丰富的应用，无论是发币，博彩还是游戏这些都离不开智能合约的运行，离不开虚拟机这个运行载体。如果你要开发一条新的区块链，无论你是否基于以太坊进行开发，虚拟机与智能合约的支持是必须要考虑的问题。为了吸引以太坊用户或者Dapp的开发和发布人员，同时也是出于基于以太坊对业务迁移成本的考虑，兼容以太坊智能合约往往都会写入到白皮书中。
对于兼容以太坊智能合约有以下两种实现方式：
* 编译器层面支持，支持将以太坊的智能合约编译成自实现的虚拟机可以操作执行的字节码
* 虚拟机层面支持，虚拟机支持解析以太坊智能合约编译成的字节码

通过简单的考虑，我们不难发现在虚拟机层面支持将是成本最低的方案。现在我们回到以太坊虚拟机，之前的文章有详细的介绍过以太坊虚拟机的实现和运行模式，对于每个智能合约的运行将创建一个新的EVM实例，这给我提供了一个思路：通过对以太坊虚拟机部分功能的剥离，这样我们就可以得到一个以太坊智能合约的运行环境，代码层面就是一个EVM的函数库。这样在新的区块链中，如果我们希望区块链兼容以太坊智能合约，我们只需要实现该函数库对外的接口，并将智能合约二进制码以参数的形式传递进去（这也是大多数虚拟机的方式），并以二进制的形式获得输出，这样我们就实现了对以太坊智能合约的兼容。
基于以上的思路，我们主要做了以下的工作：
* 剥离go-ethereum中的EVM部分代码为单独的工程
* 尽量的去除EVM中的对go-ethereum的编译依赖
* 梳理EVM中运行的对外的依赖接口
* 提供一个完整的可以二次开发的EVM，即以太坊智能合约运行环境

以上工作过程中的主要原则是尽量的使代码有少的外部依赖，这样做的主要目的一是工程上方便实现该函数库的二次开发，二是减少使用者的二次开发成本。
## 具体实现
可以在github上获取该项目的源代码，你将得到一个最小的以太坊智能合约运行环境，github地址为：https://github.com/XChainLab/evm-lite.git
工程下主要有三个目录：
* crypto为加密函数库，函数库来源于go-ethereum,这部分单独出目录
* kernal为以太坊虚拟机核心代码，实现了智能合约的运行环境，代码来自go-ethereum
* demo为一个具体的使用示例

通过demo我们来演示如何让你的区块链支持以太坊智能合约</br>
### 第一步实现数据访问接口
由于不同区块链底层依赖的数据存储不同，而以太坊智能合约中有对存储的操作，因此这里我们需要实现数据访问接口，接口的描述见文件kernal/statedb.go。
demo中我们实现了其中的部分接口,具体见mockstatedb.go，这里需要说明一下，demo中实现的是以太坊智能合约运行必须实现的接口，其他接口可以考虑不实现，必要的接口函数为如下：
```
GetCode(address kernal.Address) []byte
GetCodeHash(kernal.Address) kernal.Hash
SetCode(address kernal.Address, data []byte)
GetCodeSize(address kernal.Address) int
Exist(kernal.Address) bool
Empty(kernal.Address) bool
//关于snapshot的接口需要根据具体情况进行实现
RevertToSnapshot(int)                                             
Snapshot() int
HaveSufficientBalance(kernal.Address, *big.Int) bool
TransferBalance(kernal.Address, kernal.Address, *big.Int)
```
除此之外还要实现一个链访问的接口，具体见kernal/chain.go,这里只需要实现一个接口函数即可
```
GetBlockHeaderHash(uint64) kernal.Hash
```
### 第二步创建EVM执行实例
具体见demo/runtime.go，这里主要工作是初始化相关的配置，该项目的原则上保留了以太坊的相关配置，使用者可以根据自己的情况设置其中的具体数值，demo中采用的均是默认值，使用者可以进行参考，创建EVM部分的代码如下：
```
func CreateExecuteRuntime(caller kernal.Address) *kernal.EVM {
    context := CreateExecuteContext(caller)
    stateDB := MakeNewMockStateDB()
    chainConfig := CreateChainConfig()
    vmConfig := CreateVMDefaultConfig()
    chainHandler := new(ETHChainHandler)

    evm := kernal.NewEVM(context, stateDB, chainHandler, chainConfig, vmConfig)
    return evm
}
```
### 第三部调用智能合约
在第二步中我们创建了EVM的运行实例，这里我们通过调用EVM的Call函数直接运行代码的方式来运行智能合约
```
HexTestCode := "6060604052600a8060106000396000f360606040526008565b00"
TestInput := []byte("Contract")
TestCallerAddress := []byte("TestAddress")
TestContractAddress := []byte("TestContract")
calleraddress := kernal.BytesToAddress(TestCallerAddress)
contractaddress := kernal.BytesToAddress(TestContractAddress)
evm := CreateExecuteRuntime(calleraddress)
evm.StateDBHandler.CreateAccount(contractaddress)
evm.StateDBHandler.SetCode(contractaddress, kernal.Hex2Bytes(HexTestCode))
caller := kernal.AccountRef(evm.Origin)
ret, _, err := evm.Call(
    caller,
    contractaddress,
    TestInput,
    evm.GasLimit,
    new(big.Int))
if err != nil {
    fmt.Println(err)
} else {
    fmt.Println(ret)
}
```
这里我们直接将代码传递给了EVM，目前EVM对外的接口保留源代码中的各个接口，可以通过调用Create函数来实现创建一个智能合约。
### 编译运行
执行上面的demo十分的简单主要执行以下的几步操作即可：
* 确认你的机器上有golang的编译环境
* git clone 代码到你的机器的任何路径，无需放到GOPATH下
* 进入demo文件夹，执行go build命令
* 运行demo即可

## 总结
本文通过以上的说明提供了一个让你的区块链支持以太坊虚拟机的思路和实现方式，并提供一个EVM的纯净版本供开发者使用，使开发者可以快速的在一天的时间里完成区块链对以太坊智能合约支持的开发，后续我们将结合目前区块链虚拟机技术的发展方向，来不断的提供对虚拟机通用化的技术支持和社区贡献。
