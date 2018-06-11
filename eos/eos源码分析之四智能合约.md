# eos源码分析之四智能合约
智能合约和虚拟机部分会混合在一起讲，然后在各自的范围内偏向于哪个部分。
</br>

# 一、一个简单智能合约
</br>
智能合约的编译使用WASM来编译，也使用了一些自定义的代码用来固定智能合约的格式和入口等。智能合约产生二进制后会放到虚拟机中执行。首先看一个入门的智能合约，helloworld.
</br>

``` c++
hello.cpp：

#include<eosiolib/eosio.hpp>
#include<eosiolib/print.hpp>
usingnamespace eosio;
class hello :public eosio::contract
{
  public:using contract::contract;
  /// @abi action
  void helloworld( account_name user )
  {
    print( "Hello, ", name{user} );
  }
};
EOSIO_ABI( hello, (hi) )
```
</br>
在EOS的源码中最EOSIO_ABI被定义成：
</br>

``` c++
#define EOSIO_ABI( TYPE, MEMBERS ) \
extern "C" { \
   void apply( uint64_t receiver, uint64_t code, uint64_t action ) { \
      auto self = receiver; \
      if( code == self ) { \
         TYPE thiscontract( self ); \  //注意这个变量,后面会引用
         switch( action ) { \
            EOSIO_API( TYPE, MEMBERS ) \
         } \
         eosio_exit(0); \
      } \
   } \
} \

```
</br>
这时候再对照一下EOS自带的一个空的智能合约的例子：
</br>

``` c++
//noop.hpp
#pragma once

#include <eosiolib/eosio.hpp>
#include <eosiolib/dispatcher.hpp>

namespace noop {
   using std::string;
   /**
      noop contract
      All it does is require sender authorization.
      Actions: anyaction*/
   class noop {
      public:

         ACTION(N(noop), anyaction) {
            anyaction() { }
            anyaction(account_name f, const string& t, const string& d): from(f), type(t), data(d) { }

            account_name from;
            string type;
            string data;

            EOSLIB_SERIALIZE(anyaction, (from)(type)(data))
         };

         static void on(const anyaction& act)
         {
            require_auth(act.from);
         }
   };
} /// noop

//noop.cpp
#include <noop/noop.hpp>

namespace noop {
   extern "C" {
      /// The apply method implements the dispatch of events to this contract
      void apply( uint64_t receiver, uint64_t code, uint64_t action ) {
         eosio::dispatch<noop, noop::anyaction>(code, action);
      }
   }
}

```
</br>
通过二者的对比可以发现，其实宏EOSIO_ABI自动完成了对action的映射分发。而EOS自带的则手动实现了静态分发，结果是一样的。它们的核心其实都是apply这个函数，如果有std::bind的使用经验，发现他们还是有些类似的。
</br>
继续接着分析EOSIO_ABI的内部代码，里面调用了一个宏：
</br>

``` c++
#define EOSIO_API_CALL( r, OP, elem ) \
   case ::eosio::string_to_name( BOOST_PP_STRINGIZE(elem) ): \
      eosio::execute_action( &thiscontract, &OP::elem ); \
      return;

#define EOSIO_API( TYPE,  MEMBERS ) \
   BOOST_PP_SEQ_FOR_EACH( EOSIO_API_CALL, TYPE, MEMBERS )
```
</br>
BOOST_PP_SEQ_FOR_EACH这个宏前面讲过，是按最后一个参数展开第一个宏。再看一执行的代码：
</br>

``` c++
template<typename T, typename Q, typename... Args>
bool execute_action( T* obj, void (Q::*func)(Args...)  ) {
   size_t size = action_data_size();

   //using malloc/free here potentially is not exception-safe, although WASM doesn't support exceptions
   constexpr size_t max_stack_buffer_size = 512;
   void* buffer = max_stack_buffer_size < size ? malloc(size) : alloca(size);
   read_action_data( buffer, size );

   auto args = unpack<std::tuple<std::decay_t<Args>...>>( (char*)buffer, size );

   if ( max_stack_buffer_size < size ) {
      free(buffer);
   }

   auto f2 = [&]( auto... a ){  
      (obj->\*func)( a... ); //调用指定类对象的指定的函数，如果对照前面就是hello对象的helloworld
   };

   boost::mp11::tuple_apply( f2, args );//惰性求值
   return true;
}
```
</br>
在bancor、currency的目录下，主要是货币转换相关的部分，dice是一个掷骰子的游戏的合约。***eosio.msig,eosio.token,eosio.bios*** 都是相关的智能合约的程序，可认为是EOS自带的智能合约或者说自带的软件。
</br>

# 二、智能合约
</br>

## 1、智能合约的内容

看完了上面的代码分析，回到智能合约本身来。智能合约是什么？有几部分？怎么执行？
</br>
EOS智能合约通过messages 及 共享内存数据库（比如只要一个合约被包含在transaction的读取域中with an async vibe，它就可以读取另一个合约的数据库）相互通信。异步通信导致的spam问题将由资源限制算法来解决。下面是两个在合约里可定义的通信模型：
</br>
1、Inline:Inline保证执行当前的transaction或unwind；无论成功或失败都不会有通知。Inline 操作的scopes和authorities和原来的transaction一样。
</br>
2、Deferred: Defer将稍后由区块生产者来安排；结果可能是传递通信结果或者只是超时。Deferred可以触及不同的scopes，可以携带发送它的合约的authority*此特性在STAT不可用
</br>
message 和Transaction的关系：
</br>
一个message代表一个操作，一个Transaction中可以包含一个或者多个message，合约和帐户通过其来通信。Message既可以单独发送也可以批量发送。
</br>

```
//单MESSAGE的Transaction
{
  "ref_block_num": "100",
  "ref_block_prefix": "137469861",
  "expiration": "2017-09-25T06:28:49",
  "scope": ["initb","initc"],
  "messages": [
  {
    "code": "eos",
    "type": "transfer",
    "authorization": [
    {
      "account": "initb",
      "permission": "active"
      }
      ],
      "data": "000000000041934b000000008041934be803000000000000" }
      ],
  "signatures": [],
  "authorizations": []
}

//多Message的Transaction
{
  "ref_block_num": "100",
  "ref_block_prefix": "137469861",
  "expiration": "2017-09-25T06:28:49",
  "scope": [...],
  "messages":
  [
  {
    "code": "...",
    "type": "...",
    "authorization": [...],
  "data": "..."
  },
  {
    "code": "...",
    "type": "...",
  "authorization": [...],
  "data": "..."
  }, ...
  ],
  "signatures": [],
  "authorizations": []
}

```

</br>

## 2、Message名的限定和技术限制

Message的类型实际上是base32编码的64位整数。所以Message名的前12个字符需限制在字母a-z, 1-5, 以及'.' 。第13个以后的字符限制在前16个字符('.' and a-p)。
</br>
另外需要注意的是，在合约中不得存在浮点数，所有的Transaction必须在1ms内执行完成，否则失败。从目前来看每个帐户每秒最多发出30个Transactions。
</br>

## 3、智能合约的模块
</br>
在前面的例程里可以看到在智能合约中有apply这个函数，也知道这个函数是非常重要的，其实还有别的几个函数也挺重要：
</br>

### init
init仅在被初次部署的时候执行一次。它是用于初始化合约变量的，例如货币合约中提供token的数量。
</br>

### apply
apply是message处理器，它监听所有输入的messages并根据函数中的规定进行反馈。apply函数需要两个输入参数，code和 action。
</br>

### code filter
为了响应特定message，您可以如下构建您的apply函数。您也可以忽略code filter来构建一个响应通用messages的函数。
</br>

```
if (code == N(${contract_name}) {
    //响应特定message的处理器
}
```
</br>
在其中您可以定义对不同actions的响应。
</br>

### action filter
为了相应特定action，您可以如下构建您的apply函数。常和code filter一起使用。
</br>

```
if (action == N(${action_name}) {
    //响应该action的处理器
}
```
</br>

# 三、智能合约的编译
</br>
EOS的智能合约必须使用EOSCPP这个命令来编译，任何需要布置在EOS上的智能合约必须编译成wasm(.wast)文件，并且有一个abi的文件。wasm-jit提供了这个编译的过程，在虚拟机的部分详细的介绍一下编译和执行的过程。
</br>

# 四、智能合约的执行

在加载自定义的智能合约前，一般会加在上面提到的三个智能合约，用来测权限和相关的配置。这里看一看最基础的BIOS这个智能合约：
</br>
$ cleos set contract hello hello.wast hello.abi  

</br>
$ cleos push action hello helloworld '["fred" ]' -p hello
</br>

然后就可以在本地的nodeos节点的日志中查阅到上面的信息。
</br>

# 五、智能合约的调试

参考EOS的github上的wiki的智能合约部分，其实上面有相当一部分就是从上面摘抄下来的。

</br>
</br>
