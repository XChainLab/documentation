# eos源码分析之五虚拟机

因为6月2日，blockone团队发布了上线的源码，所以从这里开始基于最新的1.01版本来分析。</br>

## 一、虚拟机的模块

虚拟机的代码主要分散在了以下几个目录， 主要在智能合约目录contracts，一些辅助的ABI的源码,区块链目录library/chain，是一些编译的接口，library/wasm-jit目录下，是主要的文件部分，然后在externals/src下也有相当一部分的二进制编译代码。其它一些目录下也有相关的一些文件，但比较分散代码也很少。重点分析编译过程。
</br>
虚拟机的模块分成两部分，也就是编译部分和执行部分。智能合约在编译过程中会产生两个文件，一个是.wast,一个是.abi文件。

## 二、编译过程

### 1、wast文件的生成
</br>
eoscpp是编译智能合约的命令，在tools目录下，eosiocpp.in中：

``` c++
function build_contract {
    set -e
    workdir=`mktemp -d`

    if [[ ${VERBOSE} == "1" ]]; then
       PRINT_CMDS="set -x"
    fi

    ($PRINT_CMDS; mkdir $workdir/built)

    for file in $@; do
        name=`basename $file`
        filePath=`dirname $file`

        ($PRINT_CMDS; @WASM_CLANG@ -emit-llvm -O3 --std=c++14 --target=wasm32 -nostdinc \
                                   -nostdlib -nostdlibinc -ffreestanding -nostdlib -fno-threadsafe-statics -fno-rtti \
                                   -fno-exceptions -I ${EOSIO_INSTALL_DIR}/include \
                                   -I${EOSIO_INSTALL_DIR}/include/libc++/upstream/include \
                                   -I${EOSIO_INSTALL_DIR}/include/musl/upstream/include \
                                   -I${BOOST_INCLUDE_DIR} \
                                   -I $filePath \
                                   -c $file -o $workdir/built/$name
        )

    done

    ($PRINT_CMDS; @WASM_LLVM_LINK@ -only-needed -o $workdir/linked.bc $workdir/built/* \
                                   ${EOSIO_INSTALL_DIR}/usr/share/eosio/contractsdk/lib/eosiolib.bc \
                                   ${EOSIO_INSTALL_DIR}/usr/share/eosio/contractsdk/lib/libc++.bc \
                                   ${EOSIO_INSTALL_DIR}/usr/share/eosio/contractsdk/lib/libc.bc


    )
    ($PRINT_CMDS; @WASM_LLC@ -thread-model=single --asm-verbose=false -o $workdir/assembly.s $workdir/linked.bc)
    ($PRINT_CMDS; ${EOSIO_INSTALL_DIR}/bin/eosio-s2wasm -o $outname -s 16384 $workdir/assembly.s)
    ($PRINT_CMDS; ${EOSIO_INSTALL_DIR}/bin/eosio-wast2wasm $outname ${outname%.\*}.wasm -n)

    ($PRINT_CMDS; rm -rf $workdir)
    set +e
}
```
</br>
首先调用了 @WASM_CLANG@ -emit-llvm -O3的编译，这和安装LLVM和CLANG有必然的关系。然后它会调用相关的链接库，关键还是最后几行代码：
</br>bin/eosio-s2wasm和bin/eosio-wast2wasm。
</br>
从这里基本已经看出LLVM还是要和EOS内部的一些代码一起工作，才能搞定所有的流程。主要的编译工作由LLVM及其相关的模块构成，在这个过程中使用了一种叫做C++ without Emscripten的过程即：直接用 clang 的前端编译到 LLVM 的 bc，然后 llc 编译到汇编文件 s，再用 Binaryen 的工具 s2wasm 从汇编文件编译到 wasm 的 ast 文件 wast，最后用 wasm-as 编译到 wasm。
</br> 可能为了数据的通用性和更好的适配性，编译过程中的许多文件都提供了相关工具命令可以来回转换，比如a.ll和a.bc之间可以通过llvm-as和llvm-dis命令相互转换。
</br>
LLVM IR主要有三种格式：一种是在内存中的编译中间语言；一种是硬盘上存储的二进制中间语言（以.bc结尾），最后一种是可读的中间格式（以.ll结尾）。这三种中间格式是完全相等的。
</br>主要编译的流程基本如下面这样：
</br>
cpp-(CLANG+LLVM工具)-> \*.bc-(LLVM)->\*.s-（Binaryen）->s2wasm-(Binaryen)->wasm2wast--->\*.wast
</br>
</br>
abi文件在WIKI中可以找到，但是在WIKI中没有wast的相关格式，下面的wast文件的内容是从EMCC的官网上扒下来的：
</br>

``` c++
;; tests/hello_world.c:4
(drop
  (call $\_printf
    (i32.const 1144)
    (get_local $$vararg_buffer)
  )
)
;; tests/hello_world.c:5
(return
  (i32.const 0)
)
```
</br>
明白了编译流程再看源码就清楚很多了，为了保证多种数据的加载，就得写一些相关的加载的代码，举一个例子：
</br>

``` c++
class wasm_runtime_interface {
......
};
class binaryen_runtime : public eosio::chain::wasm_runtime_interface
{......};
class wavm_runtime : public eosio::chain::wasm_runtime_interface
 {.....};
```
</br>
也就是说，要保证前面说过的相关文件的正确加载，特别是好多可以互相转换的文件的加载。下面以编译一个Assembly(*.wast--->*.wasm)为例分析一下： libraries/wasm-jit/Source/Programs中的Assemble.cpp
</br>

``` c++
int commandMain(int argc,char** argv)
{
......

	// Load the WAST module.
	IR::Module module;
	if(!loadTextModule(inputFilename,module)) { return EXIT_FAILURE; }

......

	// Write the binary module.
	if(!saveBinaryModule(outputFilename,module)) { return EXIT_FAILURE; }

	return EXIT_SUCCESS;
}

```
</br>
工作其实非常简单，加载WAST的模块到中间IR，然后保存成二进制的文件。保存的那个函数非常简单没啥可说的，分析下加载：
</br>

``` c++
inline bool loadTextModule(const char* filename,IR::Module& outModule)
{
	// Read the file into a string.
	auto wastBytes = loadFile(filename);
.....

	return loadTextModule(filename,wastString,outModule);
}
inline bool loadTextModule(const char* filename,const std::string& wastString,IR::Module& outModule)
{
	std::vector<WAST::Error> parseErrors;
  //分析WASM中的模块，在webassembly中，实例都是以模块出现的，详情可看LLVM及webassembly
	WAST::parseModule(wastString.c_str(),wastString.size(),outModule,parseErrors);
	if(!parseErrors.size()) { return true; }
	else
	{
......
	}
}
bool parseModule(const char* string,Uptr stringLength,IR::Module& outModule,std::vector<Error>& outErrors)
{
  Timing::Timer timer;

  // Lex the string.
  LineInfo* lineInfo = nullptr;
  std::vector<UnresolvedError> unresolvedErrors;
  Token* tokens = lex(string,stringLength,lineInfo);
  ModuleParseState state(string,lineInfo,unresolvedErrors,tokens,outModule);

  try
  {
    // Parse (module ...)<eof>
    parseParenthesized(state,[&]
    {
      require(state,t_module);
      parseModuleBody(state);
    });
    require(state,t_eof);
  }
......
}
}
void parseModuleBody(ModuleParseState& state)
{
  const Token* firstToken = state.nextToken;

  // Parse the module's declarations.
  while(state.nextToken->type != t_rightParenthesis)
  {
    parseDeclaration(state);//直接调用声明分析,用来判断跳转到哪个部分进行具体的分析
  };

......
  IR::setDisassemblyNames(state.module,state.disassemblyNames);
}
static void parseDeclaration(ModuleParseState& state)
{
	parseParenthesized(state,[&]
	{
		switch(state.nextToken->type)
		{
      //WebAssembly 中的导入的相关符号,并进入相关的分析函数
		case t_import: parseImport(state); return true;
		case t_export: parseExport(state); return true;
		case t_global: parseGlobal(state); return true;
		case t_memory: parseMemory(state); return true;
		case t_table: parseTable(state); return true;
		case t_type: parseType(state); return true;
		case t_data: parseData(state); return true;
		case t_elem: parseElem(state); return true;
		case t_func: parseFunc(state); return true;
		case t_start: parseStart(state); return true;
		default:
			parseErrorf(state,state.nextToken,"unrecognized definition in module");
			throw RecoverParseException();
		};
	});
}
//只列举其中一个Start
static void parseStart(ModuleParseState& state)
{
	require(state,t_start);

	Reference functionRef;
	if(!tryParseNameOrIndexRef(state,functionRef))
	{
		parseErrorf(state,state.nextToken,"expected function name or index");
	}

	state.postDeclarationCallbacks.push_back([functionRef](ModuleParseState& state)
	{
		state.module.startFunctionIndex = resolveRef(state,state.functionNameToIndexMap,state.module.functions.size(),functionRef);
	});
}
//最后写IR
void setDisassemblyNames(Module& module,const DisassemblyNames& names)
{
  // Replace an existing name section if one is present, or create a new section.
  Uptr userSectionIndex = 0;
  if(!findUserSection(module,"name",userSectionIndex))
  {
    userSectionIndex = module.userSections.size();
    module.userSections.push_back({"name",{}});
  }

  ArrayOutputStream stream;

  Uptr numFunctionNames = names.functions.size();
  serializeVarUInt32(stream,numFunctionNames);

  for(Uptr functionIndex = 0;functionIndex < names.functions.size();++functionIndex)
  {
    std::string functionName = names.functions[functionIndex].name;
    serialize(stream,functionName);

    Uptr numLocalNames = names.functions[functionIndex].locals.size();
    serializeVarUInt32(stream,numLocalNames);
    for(Uptr localIndex = 0;localIndex < numLocalNames;++localIndex)
    {
      std::string localName = names.functions[functionIndex].locals[localIndex];
      serialize(stream,localName);
    }
  }

  module.userSections[userSectionIndex].data = stream.getBytes();
}
```
</br>
这里分析的比较浅，并没有深入到内部去分析，其实到内部后就是真正的词法主义啥的分析了，有兴趣可以去LLVM的官网或者EMCC的官网去看相关的资料。
</br>

### 2、abi文件的生成

</br>
abi文件是一个JSON文件，主要是解释如何将用户动作在JSON和二进制表达之间转换。ABI还解释了如何将数据库状态转换为JSON或从JSON转换数据库状态。通过ABI描述了智能合约，开发人员和用户就可以通过JSON无缝地与相关的合约进行交互。下面是从EOS的WIKI上找的ABI的文件：
</br>

``` c++
{
  "____comment": "This file was generated by eosio-abigen. DO NOT EDIT - 2018-05-07T21:16:48",
  "types": [],
  "structs": [{
      "name": "hi",
      "base": "",
      "fields": [{
          "name": "user",
          "type": "account_name"
        }
      ]  
    }
  ],
  "actions": [{
      "name": "hi",
      "type": "hi",
      "ricardian_contract": ""
    }
  ],
  "tables": [],
  "ricardian_clauses": []
}
```

</br>
在eosiocpp.in中可以看到下面的代码：
</br>

``` c++
function generate_abi {

    if [[ ! -e "$1" ]]; then
        echo "You must specify a file"
        exit 1
    fi

    context_folder=$(cd "$(dirname "$1")" ; pwd -P)

    ${ABIGEN} -extra-arg=-c -extra-arg=--std=c++14 -extra-arg=--target=wasm32 \
        -extra-arg=-nostdinc -extra-arg=-nostdinc++ -extra-arg=-DABIGEN \
        -extra-arg=-I${EOSIO_INSTALL_DIR}/include/libc++/upstream/include \
        -extra-arg=-I${EOSIO_INSTALL_DIR}/include/musl/upstream/include \
        -extra-arg=-I${BOOST_INCLUDE_DIR} \
        -extra-arg=-I${EOSIO_INSTALL_DIR}/include -extra-arg=-I$context_folder \
        -extra-arg=-fparse-all-comments -destination-file=${outname} -verbose=0 \
        -context=$context_folder $1 --

    if [ "$?" -ne 0 ]; then
        exit 1
    fi    

    echo "Generated ${outname} ..."
}
```
</br>
abi文件的生成的main程序在programs/eosio-abigen下，主要内容如下：
</br>

``` c++
using mvo = fc::mutable_variant_object;
//FrontendActionFactory 是用来产生FrontendAction的一个抽象接口，而FrontendAction又是一个Clang中的抽象的前台动作基类
std::unique_ptr<FrontendActionFactory> create_factory(bool verbose, bool opt_sfs, string abi_context, abi_def& output, const string& contract, const vector<string>& actions) {

  struct abi_frontend_action_factory : public FrontendActionFactory {

    bool                   verbose;
    bool                   opt_sfs;
    string                 abi_context;
    abi_def&               output;
    const string&          contract;
    const vector<string>&  actions;

    abi_frontend_action_factory(bool verbose, bool opt_sfs, string abi_context,
      abi_def& output, const string& contract, const vector<string>& actions) : verbose(verbose),
      abi_context(abi_context), output(output), contract(contract), actions(actions) {}

    clang::FrontendAction \*create() override {
      //创建一个generate_abi_action对象,这个对象是生成ABI的重要部分
      return new generate_abi_action(verbose, opt_sfs, abi_context, output, contract, actions);
    }

  };

  return std::unique_ptr<FrontendActionFactory>(
      new abi_frontend_action_factory(verbose, opt_sfs, abi_context, output, contract, actions)
  );
}
//这个函数用来处理接口宏
std::unique_ptr<FrontendActionFactory> create_find_macro_factory(string& contract, vector<string>& actions, string abi_context) {

  struct abi_frontend_macro_action_factory : public FrontendActionFactory {

    string&          contract;
    vector<string>&  actions;
    string           abi_context;

    abi_frontend_macro_action_factory (string& contract, vector<string>& actions,
      string abi_context ) : contract(contract), actions(actions), abi_context(abi_context) {}

    clang::FrontendAction \*create() override {
      return new find_eosio_abi_macro_action(contract, actions, abi_context);
    }

  };

  return std::unique_ptr<FrontendActionFactory>(
    new abi_frontend_macro_action_factory(contract, actions, abi_context)
  );
}
//LLVM选项处理类
static cl::OptionCategory abi_generator_category("ABI generator options");

 //扩展命令行选项,类似于增加了对选项的各种操作，如连接等
static cl::opt<std::string> abi_context(
    "context",
    cl::desc("ABI context"),
    cl::cat(abi_generator_category));

static cl::opt<std::string> abi_destination(
    "destination-file",
    cl::desc("destination json file"),
    cl::cat(abi_generator_category));

static cl::opt<bool> abi_verbose(
    "verbose",
    cl::desc("show debug info"),
    cl::cat(abi_generator_category));

static cl::opt<bool> abi_opt_sfs(
    "optimize-sfs",
    cl::desc("Optimize single field struct"),
    cl::cat(abi_generator_category));

int main(int argc, const char **argv) { abi_def output; try {
   CommonOptionsParser op(argc, argv, abi_generator_category);
   ClangTool Tool(op.getCompilations(), op.getSourcePathList());

   string contract;
   vector<string> actions;
   int result = Tool.run(create_find_macro_factory(contract, actions, abi_context).get());
   if(!result) {
      result = Tool.run(create_factory(abi_verbose, abi_opt_sfs, abi_context, output, contract, actions).get());
      if(!result) {
         abi_serializer(output).validate();
         fc::variant vabi;
         to_variant(output, vabi);

         auto comment = fc::format_string(
           "This file was generated by eosio-abigen. DO NOT EDIT - ${ts}",
           mvo("ts",fc::time_point_sec(fc::time_point::now()).to_iso_string()));

        //处理一声明内容,看一下ABI的格式就明白了
         auto abi_with_comment = mvo("____comment", comment)(mvo(vabi));
         fc::json::save_to_file(abi_with_comment, abi_destination, true);
      }
   }
   return result;
} FC_CAPTURE_AND_LOG((output)); return -1; }

```
</br>
从上面的Main函数可以看，先要查找相关的ABI宏，再根据这个宏，用工厂类创建ABI的创建对象。当然，在前面要使用CLANG的一些分析工具对象。find_eosio_abi_macro_action这个宏主要是对整个智能合约的宏进行解析：
</br>

``` c++
struct find_eosio_abi_macro_action : public PreprocessOnlyAction {

      string& contract;
      vector<string>& actions;
      const string& abi_context;

      find_eosio_abi_macro_action(string& contract, vector<string>& actions, const string& abi_context
         ): contract(contract),
         actions(actions), abi_context(abi_context) {
      }

      struct callback_handler : public PPCallbacks {

         CompilerInstance& compiler_instance;
         find_eosio_abi_macro_action& act;

         callback_handler(CompilerInstance& compiler_instance, find_eosio_abi_macro_action& act)
         : compiler_instance(compiler_instance), act(act) {}

         void MacroExpands (const Token &token, const MacroDefinition &md, SourceRange range, const MacroArgs *args) override {

            auto* id = token.getIdentifierInfo();
            if( id == nullptr ) return;
            if( id->getName() != "EOSIO_ABI" ) return;//看到这个宏没有，这是智能合约里动态创建的标志

            const auto& sm = compiler_instance.getSourceManager();
            auto file_name = sm.getFilename(range.getBegin());
            if ( !act.abi_context.empty() && !file_name.startswith(act.abi_context) ) {
               return;
            }

            ABI_ASSERT( md.getMacroInfo()->getNumArgs() == 2 );

            clang::SourceLocation b(range.getBegin()), _e(range.getEnd());
            clang::SourceLocation e(clang::Lexer::getLocForEndOfToken(\_e, 0, sm, compiler_instance.getLangOpts()));
            auto macrostr = string(sm.getCharacterData(b), sm.getCharacterData(e)-sm.getCharacterData(b));

            //正则匹配，编译器的标配
            //regex r(R"(EOSIO_ABI\s*\(\s*(.+?)\s*,((?:.+?)*)\s*\))");//注释掉是因为格式的问题 fjf 6.7
            smatch smatch;
            auto res = regex_search(macrostr, smatch, r);
            ABI_ASSERT( res );

            act.contract = smatch[1].str();

            auto actions_str = smatch[2].str();
            boost::trim(actions_str);
            actions_str = actions_str.substr(1);
            actions_str.pop_back();
            boost::remove_erase_if(actions_str, boost::is_any_of(" ("));

            boost::split(act.actions, actions_str, boost::is_any_of(")"));
         }
      };

      void ExecuteAction() override {
         getCompilerInstance().getPreprocessor().addPPCallbacks(
            llvm::make_unique<callback_handler>(getCompilerInstance(), *this)
         );
         PreprocessOnlyAction::ExecuteAction();
      };

};

```
</br>
这些个完成后，在Main函数中进行abi_serializer，最后保存到文件，ABI就这个产生了。当然，这背后的细节LLVM和CLAN做了好多，感兴趣的可以多在其官网上看看，最近看虚拟机和JAVA的对比，再和c++编译器编译对比，收益还是颇大。
</br>
最后看一下这个类： class generate_abi_action : public ASTFrontendAction{......},这个类在前边的工厂里进行了创建，但是其中有一个主要的函数
</br>

``` c++
std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance& compiler_instance,
                                               llvm::StringRef) override {
   return llvm::make_unique<abi_generator_astconsumer>(compiler_instance, abi_gen);
}
```
</br>
这个函数是内部调用的，因为，它是protected的类型。在Compile之前，创建ASTConsumer。在建立AST（抽象语法树）的过程中，ASTConsumer提供了众多的Hooks。被FrontendAction的公共接口BeginSourceFile调用。
</br>
这里最终会调用abi_generator对象，其中void abi_generator::handle_decl(const Decl* decl)这个函数，用来处理具体的细节。
</br>
</br>
</br>
</br>
</br>
</br>


## 三、执行过程

</br>
加载到虚拟机的过程其实就是JIT做的事儿了，有兴趣可以分析一下wast-jit这个文件下的部分，特别是Runtime内部的一些代码，这里主要分析一下加载过程，在programs/cleos中的主函数中：
</br>

``` c++
int main(int argc,char**argv)
{
  ......
  // set subcommand
    auto setSubcommand = app.add_subcommand("set", localized("Set or update blockchain state"));
    setSubcommand->require_subcommand();

    // set contract subcommand
    string account;
    string contractPath;
    string wastPath;
    string abiPath;
    bool shouldSend = true;
    auto codeSubcommand = setSubcommand->add_subcommand("code", localized("Create or update the code on an account"));
    codeSubcommand->add_option("account", account, localized("The account to set code for"))->required();
    codeSubcommand->add_option("code-file", wastPath, localized("The fullpath containing the contract WAST or WASM"))->required();

    auto abiSubcommand = setSubcommand->add_subcommand("abi", localized("Create or update the abi on an account"));
    abiSubcommand->add_option("account", account, localized("The account to set the ABI for"))->required();
    abiSubcommand->add_option("abi-file", abiPath, localized("The fullpath containing the contract WAST or WASM"))->required();

    auto contractSubcommand = setSubcommand->add_subcommand("contract", localized("Create or update the contract on an account"));
    contractSubcommand->add_option("account", account, localized("The account to publish a contract for"))
                      ->required();
    contractSubcommand->add_option("contract-dir", contractPath, localized("The path containing the .wast and .abi"))
                      ->required();
    contractSubcommand->add_option("wast-file", wastPath, localized("The file containing the contract WAST or WASM relative to contract-dir"));
 //                     ->check(CLI::ExistingFile);
    auto abi = contractSubcommand->add_option("abi-file,-a,--abi", abiPath, localized("The ABI for the contract relative to contract-dir"));
 //                                ->check(CLI::ExistingFile);

    //处理智能合约
    std::vector<chain::action> actions;
    auto set_code_callback = [&]() {
       std::string wast;
       fc::path cpath(contractPath);

       if( cpath.filename().generic_string() == "." ) cpath = cpath.parent_path();

       if( wastPath.empty() )
       {
          wastPath = (cpath / (cpath.filename().generic_string()+".wasm")).generic_string();
          if (!fc::exists(wastPath))
             wastPath = (cpath / (cpath.filename().generic_string()+".wast")).generic_string();
       }

       std::cout << localized(("Reading WAST/WASM from " + wastPath + "...").c_str()) << std::endl;
       fc::read_file_contents(wastPath, wast);
       FC_ASSERT( !wast.empty(), "no wast file found ${f}", ("f", wastPath) );
       vector<uint8_t> wasm;
       const string binary_wasm_header("\x00\x61\x73\x6d", 4);
       if(wast.compare(0, 4, binary_wasm_header) == 0) {
          std::cout << localized("Using already assembled WASM...") << std::endl;
          wasm = vector<uint8_t>(wast.begin(), wast.end());
       }
       else {
          std::cout << localized("Assembling WASM...") << std::endl;
          wasm = wast_to_wasm(wast);//处理可见文件与二进制的执行形式
       }

       actions.emplace_back( create_setcode(account, bytes(wasm.begin(), wasm.end()) ) );
       if ( shouldSend ) {
          std::cout << localized("Setting Code...") << std::endl;
          send_actions(std::move(actions), 10000, packed_transaction::zlib);
       }
    };

    //处理ABI的加载
    auto set_abi_callback = [&]() {
       fc::path cpath(contractPath);
       if( cpath.filename().generic_string() == "." ) cpath = cpath.parent_path();

       if( abiPath.empty() )
       {
          abiPath = (cpath / (cpath.filename().generic_string()+".abi")).generic_string();
       }

       FC_ASSERT( fc::exists( abiPath ), "no abi file found ${f}", ("f", abiPath)  );

       try {
          actions.emplace_back( create_setabi(account, fc::json::from_file(abiPath).as<abi_def>()) );
       } EOS_RETHROW_EXCEPTIONS(abi_type_exception,  "Fail to parse ABI JSON")
       if ( shouldSend ) {
          std::cout << localized("Setting ABI...") << std::endl;
          send_actions(std::move(actions), 10000, packed_transaction::zlib);
       }
    };

    add_standard_transaction_options(contractSubcommand, "account@active");
    add_standard_transaction_options(codeSubcommand, "account@active");
    add_standard_transaction_options(abiSubcommand, "account@active");
    contractSubcommand->set_callback([&] {
       shouldSend = false;
       set_code_callback();
       set_abi_callback();
       std::cout << localized("Publishing contract...") << std::endl;
       send_actions(std::move(actions), 10000, packed_transaction::zlib);
    });
    codeSubcommand->set_callback(set_code_callback);
    abiSubcommand->set_callback(set_abi_callback);
  ......
}
```
</br>
这里只分析一下wast->wasm的转换：
</br>

``` c++
std::vector<uint8_t> wast_to_wasm( const std::string& wast )
{
   std::stringstream ss;

   try {
   IR::Module module; //中间语言
   std::vector<WAST::Error> parse_errors;
   //这里用到了jit的对象
   WAST::parseModule(wast.c_str(),wast.size(),module,parse_errors);//以Module为单元分析文件中的数据
......
   //按照LLVM的编译要求处理节
   for(auto sectionIt = module.userSections.begin();sectionIt != module.userSections.end();++sectionIt)
   {
      if(sectionIt->name == "name") { module.userSections.erase(sectionIt); break; }
   }

   try
   {
      // Serialize the WebAssembly module.串行化，其实就是二进制化
      Serialization::ArrayOutputStream stream;
      WASM::serialize(stream,module);
      return stream.getBytes();
   }
   catch(const Serialization::FatalSerializationException& exception)
   {
      ss << "Error serializing WebAssembly binary file:" << std::endl;
      ss << exception.message << std::endl;
      FC_ASSERT( !"error converting to wasm", "${msg}", ("msg",ss.get()) );
   } catch(const IR::ValidationException& e) {
      ss << "Error validating WebAssembly binary file:" << std::endl;
      ss << e.message << std::endl;
      FC_ASSERT( !"error converting to wasm", "${msg}", ("msg",ss.get()) );
   }

} FC_CAPTURE_AND_RETHROW( (wast) ) }  /// wast_to_wasm
//其下两个是分别处理不同类型的文件来源
std::string     wasm_to_wast( const std::vector<uint8_t>& wasm ) {
   return wasm_to_wast( wasm.data(), wasm.size() );
} /// wasm_to_wast

std::string     wasm_to_wast( const uint8_t* data, uint64_t size )
{ try {
    IR::Module module;
    Serialization::MemoryInputStream stream((const U8*)data,size);
    WASM::serialize(stream,module);
     // Print the module to WAST.
    return WAST::print(module);
} FC_CAPTURE_AND_RETHROW() }
```
</br>
基本到现在就把虚拟机简要的分析了一下，其中有好多关于CLANG,LLVM和Webassembly的知识，需要在看这篇文章前了解一下。
</br>
