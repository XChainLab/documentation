# EOS对WASM的支持

## 一、EOS为什么选择WASM
EOS为什么选择在虚拟机中使用WASM，主要的原因就是：
</br>
1、支持C/C++等高级语言，效率高。
</br>
2、由于多语言的兼容性导致学习的成本大大降低。基本所有语言的人都可以写智能合约。
</br>
3、谷歌、苹果、微软等大公司的强有力支持。
</br>
4、既支持解释型虚拟机又支持直接编译成机器码执行，既考虑了性能又兼顾了兼容性。
</br>
5、WASM在持续迭代中，而EOS也在持续迭代中。所以影响较小。
</br>
通过上面的几点，可以看出，EOS其实最主要还是从效率和生态来考虑的，选择WASM，意味着开发这一块的生态，基本已经成型，不用考虑再引进大量的工作对其进行建设，对比以太坊的SOLIDITY，就可以看出来它的优势所在。

## 二、eos的合约例程编译
EOS的智能合约是用c++开发的（当然，目前也出现了很多其它语言的版本），通过LLVM来进行编译生成WASM。下面先看一个例子：
</br>

```C++
#include <eosiolib/eosio.hpp>

using namespace eosio;

CONTRACT hello : public eosio::contract {
  public:
      using contract::contract;

      ACTION hi( name user ) {
         print( "Hello, ", name{user} );
      }
};

EOSIO_DISPATCH( hello, (hi) )

//wasm
"0061736d01000000013e0c60027......0b0438200000"
//wast
(module
(type (;0;) (func (param i32 i64)))
(type (;1;) (func (param i32 i32)))
(type (;2;) (func (param i32 i32 i32) (result i32)))
(type (;3;) (func (result i32)))
(type (;4;) (func (param i32 i32) (result i32)))
(type (;5;) (func (param i32)))
(type (;6;) (func (param i64)))
(type (;7;) (func))
(type (;8;) (func (param i32) (result i32)))
(type (;9;) (func (param i64 i64 i64)))
(type (;10;) (func (param i64 i64 i32) (result i32)))
(type (;11;) (func (param i64 i64)))
(import "env" "eosio_assert" (func (;0;) (type 1)))
(import "env" "memset" (func (;1;) (type 2)))
(import "env" "action_data_size" (func (;2;) (type 3)))
(import "env" "read_action_data" (func (;3;) (type 4)))
(import "env" "memcpy" (func (;4;) (type 2)))
(import "env" "prints" (func (;5;) (type 5)))
(import "env" "printn" (func (;6;) (type 6)))
(import "env" "eosio_assert_code" (func (;7;) (type 0)))
(func (;8;) (type 7)
call 11)
(func (;9;) (type 8) (param i32) (result i32)
(local i32 i32 i32)
block  ;; label = @1
  block  ;; label = @2
    block  ;; label = @3
      block  ;; label = @4
        get_local 0
        i32.eqz
        br_if 0 (;@4;)
        i32.const 0
        i32.const 0
        i32.load offset=8204
        get_local 0
        i32.const 16
        i32.shr_u
        tee_local 1
        i32.add
        tee_local 2
        i32.store offset=8204
        i32.const 0
        i32.const 0
        i32.load offset=8196
        tee_local 3
        get_local 0
        i32.add
        i32.const 7
        i32.add
        i32.const -8
        i32.and
        tee_local 0
        i32.store offset=8196
        get_local 2
        i32.const 16
        i32.shl
        get_local 0
        i32.le_u
        br_if 1 (;@3;)
        get_local 1
        memory.grow
        i32.const -1
        i32.eq
        br_if 2 (;@2;)
        br 3 (;@1;)
      end
      i32.const 0
      return
    end
    i32.const 0
    get_local 2
    i32.const 1
    i32.add
    i32.store offset=8204
    get_local 1
    i32.const 1
    i32.add
    memory.grow
    i32.const -1
    i32.ne
    br_if 1 (;@1;)
  end
  i32.const 0
  i32.const 8208
  call 0
  get_local 3
  return
end
get_local 3)
(func (;10;) (type 5) (param i32))
(func (;11;) (type 7)
......
i32.add
set_global 0)
(table (;0;) 2 2 anyfunc)
(memory (;0;) 1)
(global (;0;) (mut i32) (i32.const 8192))
(global (;1;) i32 (i32.const 8246))
(global (;2;) i32 (i32.const 8246))
(export "apply" (func 13))
(elem (i32.const 1) 14)
(data (i32.const 8208) "failed to allocate pages\00Hello, \00")
(data (i32.const 8241) "read\00")
(data (i32.const 0) "8 \00\00"))
```
</br>
一个标准的入门的智能合约，后面的编译结果由于篇幅太长，省略了大部分。下面提供了几个在线的EOS智能合约IDE：
</br>
https://beosin.com/BEOSIN-IDE/index.html#/
</br>
https://tbfleming.github.io/cib/eos-slim.html
</br>
https://app.eosstudio.io/
</br>
在EOS虚拟机中，其实就是对上述编译结果的执行过程，如果大家有过解释型虚拟机的经验理解起来就很容易了。下面针对这个例子，来分析一下JIT，在前面的Webassembly中，说明了，LLVM做为一种新的编译器，它采用的与传统的编译器的方式不同，LLVM采用了分段式编译，提供了一个层中间代码IR，搭起了前端到后端的桥梁，同样，也正是采用了这种机制，使得LLVM的兼容性和适应性大大提高。
在Webassembly中正是借鉴了这种方式，也提出了一种更低级的中间代码BYTECODE（字节码），通过字节码来实现更好的适应性。看一下上面的代码片段：
</br>

```C++
(func (;9;) (type 8) (param i32) (result i32)
(local i32 i32 i32)
```
</br>
在代码中，可以通过get_local得到局部变量，通过get_global得到全局变量，后面跟0（即get_local 0）表示参数的索引序列，比如上面的例子就可以i32,1表示i32...依次类推。这个和汇编语言中拿取参数有些类似。
</br>
从上面的wast中，可以到前面分析的Webassembly中的各种数据结构和接口。如果有兴趣，可以结合着官方的文档仔细的分析一下，这些东西都是固定的，没有什么技术可言，这里就不再展开分析。
</br>
如果使用的编译器只提供了二进制的代码，不好分析的话，可以使用提供的工具集WABT（里面很多相关的处理工具）来处理一下，举一个例子：
</br>
用来查看类似反编译的详细内容：
</br>
./wat2wasm firstExample.wat -v
</br>
用来将wast转换成wasm：
</br>
wat2wasm firstExample.wast -o firstExample.wasm
</br>
更多的功能，请查看此工具集的具体的应用方法，地址在：
</br>
https://github.com/WebAssembly/wabt/
</br>
接下来分析一下EOS的虚拟机。

## 三、eos虚拟机wasm-jit
虚拟机的主要代码在libraries/wasm-jit/Source目录下，目前EOS虚拟对上面提到的WASM和WAST两种格式都是支持的。因为EOS的更新速度太快，所以有些说明可能就过时了，大家如果发现这种情况，请及时跟上EOSIO的官网即可。目前来看，EOS的虚拟有两块，一块是WAVM版本：
</br>
https://github.com/EOSIO/WAVM
</br>
一块是新独立出来的EOS-VM部分：
</br>
https://github.com/EOSIO/eos-vm
</br>
因为第二部分还不敢确定到底有没有应用到EOS上，所以暂时以第一部分分析。EOS选择WASM是出于综合的考虑的。虽然说完全套用LLVM会更简单，但这会有一个问题，就是直接和LLVM绑定。这一定不是EOS设计者们考虑问题的结果。所以，只能是牺牲一下效率，达到所谓的平衡。
</br>
先看一下虚拟机暴露的接口：
</br>

```C++
namespace eosio { namespace chain {

class apply_context;

class wasm_instantiated_module_interface {
   public:
      virtual void apply(apply_context& context) = 0;

      virtual ~wasm_instantiated_module_interface();
};

class wasm_runtime_interface {
   public:
      virtual std::unique_ptr<wasm_instantiated_module_interface> instantiate_module(const char* code_bytes, size_t code_size, std::vector<uint8_t> initial_memory) = 0;

      //immediately exit the currently running wasm_instantiated_module_interface. Yep, this assumes only one can possibly run at a time.
      virtual void immediately_exit_currently_running_module() = 0;

      virtual ~wasm_runtime_interface();
};

}}

//其下为实现
//创建一个unique_ptr的独占实例指针
std::unique_ptr<wasm_instantiated_module_interface> wavm_runtime::instantiate_module(const char* code_bytes, size_t code_size, std::vector<uint8_t> initial_memory) {
   std::unique_ptr<Module> module = std::make_unique<Module>();
   try {
      Serialization::MemoryInputStream stream((const U8*)code_bytes, code_size);
      WASM::serialize(stream, *module);
   } catch(const Serialization::FatalSerializationException& e) {
      EOS_ASSERT(false, wasm_serialization_error, e.message.c_str());
   } catch(const IR::ValidationException& e) {
      EOS_ASSERT(false, wasm_serialization_error, e.message.c_str());
   }

   eosio::chain::webassembly::common::root_resolver resolver;
   LinkResult link_result = linkModule(*module, resolver);
   ModuleInstance \*instance = instantiateModule(*module, std::move(link_result.resolvedImports));
   EOS_ASSERT(instance != nullptr, wasm_exception, "Fail to Instantiate WAVM Module");

   return std::make_unique<wavm_instantiated_module>(instance, std::move(module), initial_memory);
}
//实现Apply
void apply(apply_context& context) override {
   vector<Value> args = {Value(uint64_t(context.get_receiver())),
                        Value(uint64_t(context.get_action().account)),
                         Value(uint64_t(context.get_action().name))};

   call("apply", args, context);
}

private:
void call(const string &entry_point, const vector <Value> &args, apply_context &context) {
   try {
      FunctionInstance* call = asFunctionNullable(getInstanceExport(\_instance,entry_point));
      if( !call )
         return;

      EOS_ASSERT( getFunctionType(call)->parameters.size() == args.size(), wasm_exception, "" );

      MemoryInstance* default_mem = getDefaultMemory(\_instance);
      if(default_mem) {
         //reset memory resizes the sandbox'ed memory to the module's init memory size and then
         // (effectively) memzeros it all
         resetMemory(default_mem, \_initial_memory_config);

         char* memstart = &memoryRef<char>(getDefaultMemory(\_instance), 0);
         memcpy(memstart, \_initial_memory.data(), \_initial_memory.size());
      }

      the_running_instance_context.memory = default_mem;
      the_running_instance_context.apply_ctx = &context;

      resetGlobalInstances(\_instance);
      runInstanceStartFunc(\_instance);
      Runtime::invokeFunction(call,args);
   } catch( const wasm_exit& e ) {
   } catch( const Runtime::Exception& e ) {
       FC_THROW_EXCEPTION(wasm_execution_error,
                   "cause: ${cause}\n${callstack}",
                   ("cause", string(describeExceptionCause(e.cause)))
                   ("callstack", e.callStack));
   } FC_CAPTURE_AND_RETHROW()
}
```
接口很简单，只有三个函数，apply、instantiate_module和immediately_exit_currently_running_module。在EOS的智能合约中apply接口是必须实现的（通过EOSIO_ABI宏来实现）。程序的两个主要接口首先产生个接口实例的独占指针。然后在apply中调用call函数。在apply中，会得到三个相关的参数，即代码，帐户和action的名称。
</br>
在call函数中，首先得到call函数指针，通过MemoryInstance指针得到公用的WASM模块的内存实例。将其重置并初始化，绑定到相关的上下文信息中。重置相关的全局变量。然后调用模块的起始函数（这个在前面WASM中介绍过，可有可无，根据实际情况来定），接着调用EOB_ABI的apply函数。这样整个的虚拟机的核心流程就清楚了。
执行时是要生成IR中间语言来处理，看一下IR的部分：
</br>

```C++
IR::Module module;
try {
   Serialization::MemoryInputStream stream((const U8*)codeobject->code.data(), codeobject->code.size());
   WASM::serialize(stream, module);
   module.userSections.clear();
} catch(const Serialization::FatalSerializationException& e) {
   EOS_ASSERT(false, wasm_serialization_error, e.message.c_str());
} catch(const IR::ValidationException& e) {
   EOS_ASSERT(false, wasm_serialization_error, e.message.c_str());
}

//WASMSerializatin.cpp中有很多的重载实现
void serializeModule(InputStream& moduleStream,Module& module)
{
  serializeConstant(moduleStream,"magic number",U32(magicNumber));
  serializeConstant(moduleStream,"version",U32(currentVersion));

  SectionType lastKnownSectionType = SectionType::unknown;
  while(moduleStream.capacity())
  {
    const SectionType sectionType = *(SectionType*)moduleStream.peek(sizeof(SectionType));
    if(sectionType != SectionType::user)
    {
      if(sectionType > lastKnownSectionType) { lastKnownSectionType = sectionType; }
      else { throw FatalSerializationException("incorrect order for known section"); }
    }
    switch(sectionType)
    {
    case SectionType::type: serializeTypeSection(moduleStream,module); break;
    case SectionType::import: serializeImportSection(moduleStream,module); break;
    case SectionType::functionDeclarations: serializeFunctionSection(moduleStream,module); break;
    case SectionType::table: serializeTableSection(moduleStream,module); break;
    case SectionType::memory: serializeMemorySection(moduleStream,module); break;
    case SectionType::global: serializeGlobalSection(moduleStream,module); break;
    case SectionType::export_: serializeExportSection(moduleStream,module); break;
    case SectionType::start: serializeStartSection(moduleStream,module); break;
    case SectionType::elem: serializeElementSection(moduleStream,module); break;
    case SectionType::functionDefinitions: serializeCodeSection(moduleStream,module); break;
    case SectionType::data: serializeDataSection(moduleStream,module); break;
    case SectionType::user:
    {
      UserSection& userSection = \*module.userSections.insert(module.userSections.end(),UserSection());
      serialize(moduleStream,userSection);
      break;
    }
    default: throw FatalSerializationException("unknown section ID");
    };
  };
}

```
</br>
到这里就应该明白怎么做了吧。其实就是对具体的Webassmbly的不同的节进行不同的处理。更具体的代码请关注EOS的相关源码。
</br>
智能合约的整体流程，包括部署、调用、存储和执行。执行的核心部分前边分析了，部署、存储和虚拟机不是很紧密，下来看一下调用:
</br>
调用，在EOS中，交易的分发是通过void transaction_context::execute_action这个函数来处理action的（交易如何最终传到此处，可以查看代码相关部分），再调用exec,直到exec_one:
</br>

```C++
{
   receiver_account = &db.get<account_metadata_object,by_name>( receiver );
   privileged = receiver_account->is_privileged();
   auto native = control.find_apply_handler( receiver, act->account, act->name );
   if( native ) {
      if( trx_context.enforce_whiteblacklist && control.is_producing_block() ) {
         control.check_contract_list( receiver );
         control.check_action_list( act->account, act->name );
      }
      (\*native)( \*this );
   }

   if( ( receiver_account->code_hash != digest_type() ) &&
         (  !( act->account == config::system_account_name
               && act->name == N( setcode )
               && receiver == config::system_account_name )
            || control.is_builtin_activated( builtin_protocol_feature_t::forward_setcode )
         )
   ) {
      if( trx_context.enforce_whiteblacklist && control.is_producing_block() ) {
         control.check_contract_list( receiver );
         control.check_action_list( act->account, act->name );
      }
      try {
         control.get_wasm_interface().apply( receiver_account->code_hash, receiver_account->vm_type, receiver_account->vm_version, *this );
      } catch( const wasm_exit& ) {}
   }
```
</br>
在合约的调用过程中，分成两种情况，即本地（系统）合约，像发币的合约，同样也有自己部署的合约。这里看后者，注意最后的apply的调用。而apply函数是通过设置Handler来实现的：
</br>

```C++
#define SET_APP_HANDLER( receiver, contract, action) \
   set_apply_handler( #receiver, #contract, #action, &BOOST_PP_CAT(apply_, BOOST_PP_CAT(contract, BOOST_PP_CAT(_,action) ) ) )

   SET_APP_HANDLER( eosio, eosio, newaccount );
   SET_APP_HANDLER( eosio, eosio, setcode );
   SET_APP_HANDLER( eosio, eosio, setabi );
   SET_APP_HANDLER( eosio, eosio, updateauth );
   SET_APP_HANDLER( eosio, eosio, deleteauth );
   SET_APP_HANDLER( eosio, eosio, linkauth );
   SET_APP_HANDLER( eosio, eosio, unlinkauth );
/*
   SET_APP_HANDLER( eosio, eosio, postrecovery );
   SET_APP_HANDLER( eosio, eosio, passrecovery );
   SET_APP_HANDLER( eosio, eosio, vetorecovery );
*/

   SET_APP_HANDLER( eosio, eosio, canceldelay );
   }
//看find_apply_handler的对应注册机制
void set_apply_handler( account_name receiver, account_name contract, action_name action, apply_handler v ) {
   apply_handlers[receiver][make_pair(contract,action)] = v;
}
```
</br>
继续看apply:
</br>

```C++
void wasm_interface::apply( const digest_type& code_hash, const uint8_t& vm_type, const uint8_t& vm_version, apply_context& context ) {
   my->get_instantiated_module(code_hash, vm_type, vm_version, context.trx_context)->apply(context);
}
```
</br>
这下就明白了，调用init的模块，然后再调用相关的apply.这其实就是一个查询相关的合约实例，然后再通过此实例调用其自身的apply.一路下来真的好绕口。从执行action，到查找注册的handler，执行系统合约，通过apply执行部署的合约。
</br>
再来看一下WAVM的解释器（Binaryen的与其类似），前面提到过三个接口，其中一个就是生成实例的，代码最后：
</br>

```C++
std::unique_ptr<wasm_instantiated_module_interface> wavm_runtime::instantiate_module(const char* code_bytes, size_t code_size, std::vector<uint8_t> initial_memory) {
   std::unique_ptr<Module> module = std::make_unique<Module>();
......
   return std::make_unique<wavm_instantiated_module>(instance, std::move(module), initial_memory);
}
//会调用
ModuleInstance* instantiateModule(const IR::Module& module,ImportBindings&& imports)
{
  ......
  // Generate machine code for the module.
  //这里调用LLVMJIT，为后来编译提供资源
  LLVMJIT::instantiateModule(module,moduleInstance);

  // Set up the instance's exports.
  for(const Export& exportIt : module.exports)
  {
    ObjectInstance* exportedObject = nullptr;
    switch(exportIt.kind)
    {
    case ObjectKind::function: exportedObject = moduleInstance->functions[exportIt.index]; break;
    case ObjectKind::table: exportedObject = moduleInstance->tables[exportIt.index]; break;
    case ObjectKind::memory: exportedObject = moduleInstance->memories[exportIt.index]; break;
    case ObjectKind::global: exportedObject = moduleInstance->globals[exportIt.index]; break;
    default: Errors::unreachable();
    }
    moduleInstance->exportMap[exportIt.name] = exportedObject;
  }
......
}
void instantiateModule(const IR::Module& module,ModuleInstance* moduleInstance)
{
  // Emit LLVM IR for the module.
  auto llvmModule = emitModule(module,moduleInstance);

  // Construct the JIT compilation pipeline for this module.
  auto jitModule = new JITModule(moduleInstance);
  moduleInstance->jitModule = jitModule;

  // Compile the module.
  jitModule->compile(llvmModule);
}
```
</br>
看到最后一行没有，其实是调用的LLVMJIT的编译方法，编译完成后，开始对apply的处理，这个函数在前面核心流程时提到过：
</br>

```C++
void call(const string &entry_point, const vector <Value> &args, apply_context &context) {
   try {
      FunctionInstance* call = asFunctionNullable(getInstanceExport(\_instance,entry_point));
      ......
      Runtime::invokeFunction(call,args);
    }
......
}
```
</br>
这里重点看第一行和最后一行，调用的函数：
</br>

```C++
Result invokeFunction(FunctionInstance* function,const std::vector<Value>& parameters)
{
  const FunctionType* functionType = function->type;

  // Check that the parameter types match the function, and copy them into a memory block that stores each as a 64-bit value.
  //参数检测
  if(parameters.size() != functionType->parameters.size())
  {
     throw Exception {Exception::Cause::invokeSignatureMismatch};
  }

  //分配主要的内存——参数的大小+返回值大小
  U64* thunkMemory = (U64*)alloca((functionType->parameters.size() + getArity(functionType->ret)) * sizeof(U64));
  //参数的安全检测
  for(Uptr parameterIndex = 0;parameterIndex < functionType->parameters.size();++parameterIndex)
  {
    if(functionType->parameters[parameterIndex] != parameters[parameterIndex].type)
    {
      throw Exception {Exception::Cause::invokeSignatureMismatch};
    }

    thunkMemory[parameterIndex] = parameters[parameterIndex].i64;
  }

  // Get the invoke thunk for this function type.
  //获得执行函数指针
  LLVMJIT::InvokeFunctionPointer invokeFunctionPointer = LLVMJIT::getInvokeThunk(functionType);

  // Catch platform-specific runtime exceptions and turn them into Runtime::Values.
  Result result;
  Platform::HardwareTrapType trapType;
  Platform::CallStack trapCallStack;
  Uptr trapOperand;
  //下面这一大段LAMBADA表达式类似于CallBack的调用
  trapType = Platform::catchHardwareTraps(trapCallStack,trapOperand,
    [&]
    {
      // Call the invoke thunk.
      (\*invokeFunctionPointer)(function->nativeFunction,thunkMemory);

      // Read the return value out of the thunk memory block.
      if(functionType->ret != ResultType::none)
      {
        result.type = functionType->ret;
        result.i64 = thunkMemory[functionType->parameters.size()];
      }
    });

  // If there was no hardware trap, just return the result.
  if(trapType == Platform::HardwareTrapType::none) { return result; }
  else { handleHardwareTrap(trapType,std::move(trapCallStack),trapOperand); }
}
```
</br>
这样，一个WAVM的执行过程就基本完成了。再到深处，可以参考LLVMJIT的实现机制，这里就不再展开，有兴趣的可以参考相关官网或者开发者文档。

## 四、总结
这里主要从调用和执行两条线进行了分析，同时辅以了IR的生成的分析过程。EOS的虚拟机的迭代速度应该和EOS本身一样，不断的变化的着，但是如果不迭代到EOS-VM，则变化就不会有颠覆性的。以后有机会仔细分析一下EOS-VM,这个以头文件形式形成的虚拟机的库，据说执行速度提高了很多倍。
