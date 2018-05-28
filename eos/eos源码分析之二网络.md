# eos源码分析之二网络
</br>

# 一、网络的初始化和启动
</br>
P2P网络是区块链的运行的基础模块，在EOS中，主要就是net_plugin,http_plugin,net_pai_plugin,当然在这个过程中网络也会引用到其它的一些模块的接口，但为了清晰，重点介绍网络相关部分，其它略过。
</br>
首先看一下网络插件生成的时候的代码：
</br>

``` c++
net_plugin::net_plugin()
   :my( new net_plugin_impl ) {
   my_impl = my.get();//此处写得不是太好，从智能指针又退化回到 普通指针
}
```
</br>
可以看到，它生成了一个net_plugin_impl的实例，真正的网络操作相关的代码其实在这个类中，看名字也可以明白，JAVA接口经常这么干。然后接着按Main函数中的初始化来看：
</br>

``` c++
void net_plugin::plugin_initialize( const variables_map& options ) {
......//日志相关忽略

   //初始化相关参数，版本，是否发送完整块，交易周期等
   my->network_version = static_cast<uint16_t>(app().version());
   my->network_version_match = options.at("network-version-match").as<bool>();
   my->send_whole_blocks = def_send_whole_blocks;

   my->sync_master.reset( new sync_manager(options.at("sync-fetch-span").as<uint32_t>() ) );
   my->big_msg_master.reset( new big_msg_manager );

   my->connector_period = std::chrono::seconds(options.at("connection-cleanup-period").as<int>());
   my->txn_exp_period = def_txn_expire_wait;
   my->resp_expected_period = def_resp_expected_wait;
   my->big_msg_master->just_send_it_max = def_max_just_send;
   my->max_client_count = options.at("max-clients").as<int>();

   my->num_clients = 0;
   my->started_sessions = 0;

   //使用BOOST的resolver来处理与网络相关的数据格式的转换
   my->resolver = std::make_shared<tcp::resolver>( std::ref( app().get_io_service() ) );

   //根据options设置来设置相关配置
   if(options.count("p2p-listen-endpoint")) {
      my->p2p_address = options.at("p2p-listen-endpoint").as< string >();
      auto host = my->p2p_address.substr( 0, my->p2p_address.find(':') );
      auto port = my->p2p_address.substr( host.size()+1, my->p2p_address.size() );
      idump((host)(port));
      tcp::resolver::query query( tcp::v4(), host.c_str(), port.c_str() );
      // Note: need to add support for IPv6 too?
      //得到监听地址
      my->listen_endpoint = \*my->resolver->resolve( query);
      //重置boost socket网络接收器
      my->acceptor.reset( new tcp::acceptor( app().get_io_service() ) );
   }
   if(options.count("p2p-server-address")) {
      my->p2p_address = options.at("p2p-server-address").as< string >();
   }
   else {
      if(my->listen_endpoint.address().to_v4() == address_v4::any()) {
         boost::system::error_code ec;
         auto host = host_name(ec);
         if( ec.value() != boost::system::errc::success) {

            FC_THROW_EXCEPTION( fc::invalid_arg_exception,
                                "Unable to retrieve host_name. ${msg}",( "msg",ec.message()));

         }
         auto port = my->p2p_address.substr( my->p2p_address.find(':'), my->p2p_address.size());
         my->p2p_address = host + port;
      }
   }
   ......
   //处理连接设置
   if(options.count("allowed-connection")) {
      const std::vector<std::string> allowed_remotes = options["allowed-connection"].as<std::vector<std::string>>();
      for(const std::string& allowed_remote : allowed_remotes)
         {
            if(allowed_remote == "any")
               my->allowed_connections |= net_plugin_impl::Any;
            else if(allowed_remote == "producers")
               my->allowed_connections |= net_plugin_impl::Producers;
            else if(allowed_remote == "specified")
               my->allowed_connections |= net_plugin_impl::Specified;
            else if(allowed_remote == "none")
               my->allowed_connections = net_plugin_impl::None;
         }
   }
......
   //查找依赖的链插件
   my->chain_plug = app().find_plugin<chain_plugin>();//插件已经在上一篇中讲过的宏中注册
   my->chain_plug->get_chain_id(my->chain_id);
   fc::rand_pseudo_bytes(my->node_id.data(), my->node_id.data_size());
   ilog("my node_id is ${id}",("id",my->node_id));
   //重置心跳定时器
   my->keepalive_timer.reset(new boost::asio::steady_timer(app().get_io_service()));
   my->ticker();
}
```
</br>
初始化完成后，看一下启动的代码
</br>

``` c++
void net_plugin::plugin_startup() {
   if( my->acceptor ) {
      常见的网络服务操作，打开监听服务，设置选项，绑定地址，启动监听
      my->acceptor->open(my->listen_endpoint.protocol());
      my->acceptor->set_option(tcp::acceptor::reuse_address(true));
      my->acceptor->bind(my->listen_endpoint);
      my->acceptor->listen();
      ilog("starting listener, max clients is ${mc}",("mc",my->max_client_count));
      my->start_listen_loop();//循环接收连接
   }

   //绑定等待交易信号
   my->chain_plug->chain().on_pending_transaction.connect( &net_plugin_impl::transaction_ready);
   my->start_monitors();//启动连接和交易到期的监视（一个自循环）

   for( auto seed_node : my->supplied_peers ) {
      connect( seed_node );//连接种子节点，接入P2P网络
   }
}
```
</br>
代码看上去很少，其实信息量真的不小。下面分别来说明。
</br>

# 二、网络的监听和接收
</br>
先看一下循环监听，写得跟别人不一样，但是目的达到的是一样。
</br>

``` c++
void net_plugin_impl::start_listen_loop( ) {
   auto socket = std::make_shared<tcp::socket>( std::ref( app().get_io_service() ) );
    //异步监听的lambada表达式
   acceptor->async_accept( *socket, [socket,this]( boost::system::error_code ec ) {
         if( !ec ) {
            uint32_t visitors = 0;
            for (auto &conn : connections) {
               if(conn->current() && conn->peer_addr.empty()) {
                  visitors++;
               }
            }
            //判断新连接并增加计数
            if (num_clients != visitors) {
               ilog ("checking max client, visitors = ${v} num clients ${n}",("v",visitors)("n",num_clients));
               num_clients = visitors;
            }
            if( max_client_count == 0 || num_clients < max_client_count ) {
               ++num_clients;
               connection_ptr c = std::make_shared<connection>( socket );
               connections.insert( c );//保存新连接的指针
               start_session( c );
            } else {
               elog( "Error max_client_count ${m} exceeded",
                     ( "m", max_client_count) );
               socket->close( );
            }
            start_listen_loop();//继续监听
         } else {
            elog( "Error accepting connection: ${m}",( "m", ec.message() ) );
         }
      });
}
void net_plugin_impl::start_session( connection_ptr con ) {
   boost::asio::ip::tcp::no_delay nodelay( true );
   con->socket->set_option( nodelay );
   start_read_message( con );//开始读取连接的消息
   ++started_sessions;

   // for now, we can just use the application main loop.
   //     con->readloop_complete  = bf::async( [=](){ read_loop( con ); } );
   //     con->writeloop_complete = bf::async( [=](){ write_loop con ); } );
}
```
其实上面的代码没什么特殊的，只是引用了BOOST的库，可能得熟悉一下，接着看如何读取消息，真正的数据交互在这里：
</br>

``` c++
void net_plugin_impl::start_read_message( connection_ptr conn ) {

   try {
      if(!conn->socket) {
         return;
      }
      //真正的数据异步读取
      conn->socket->async_read_some
         (conn->pending_message_buffer.get_buffer_sequence_for_boost_async_read(),
          [this,conn]( boost::system::error_code ec, std::size_t bytes_transferred ) {
            try {
               if( !ec ) {
                 //判断是否超大小读取数据
                  if (bytes_transferred > conn->pending_message_buffer.bytes_to_write()) {
                     elog("async_read_some callback: bytes_transfered = ${bt}, buffer.bytes_to_write = ${btw}",
                          ("bt",bytes_transferred)("btw",conn->pending_message_buffer.bytes_to_write()));
                  }
                  //判断是不是符合情况
                  FC_ASSERT(bytes_transferred <= conn->pending_message_buffer.bytes_to_write());
                  conn->pending_message_buffer.advance_write_ptr(bytes_transferred);
                  //处理数据
                  while (conn->pending_message_buffer.bytes_to_read() > 0) {
                     uint32_t bytes_in_buffer = conn->pending_message_buffer.bytes_to_read();

                     if (bytes_in_buffer < message_header_size) {
                        break;
                     } else {
                        uint32_t message_length;
                        auto index = conn->pending_message_buffer.read_index();
                        conn->pending_message_buffer.peek(&message_length, sizeof(message_length), index);
                        if(message_length > def_send_buffer_size*2) {
                           elog("incoming message length unexpected (${i})", ("i", message_length));
                           close(conn);
                           return;
                        }
                        if (bytes_in_buffer >= message_length + message_header_size) {
                           conn->pending_message_buffer.advance_read_ptr(message_header_size);
                           if (!conn->process_next_message(*this, message_length)) {
                              return;
                           }
                        } else {
                           conn->pending_message_buffer.add_space(message_length + message_header_size - bytes_in_buffer);
                           break;
                        }
                     }
                  }
                  start_read_message(conn);//继续读取
               } else {
                  auto pname = conn->peer_name();
                  if (ec.value() != boost::asio::error::eof) {
                     elog( "Error reading message from ${p}: ${m}",("p",pname)( "m", ec.message() ) );
                  } else {
                     ilog( "Peer ${p} closed connection",("p",pname) );
                  }
                  close( conn );
               }
            }
            catch(const std::exception &ex) {
......
            }
......
         } );
   } catch (...) {
......
   }
}

/*
 *  创建一个数据接收的缓冲区
 *  Creates and returns a vector of boost mutable_buffers that can
 *  be passed to boost async_read() and async_read_some() functions.
 *  The beginning of the vector will be the write pointer, which
 *  should be advanced the number of bytes read after the read returns.
 */
std::vector<boost::asio::mutable_buffer> get_buffer_sequence_for_boost_async_read() {
  std::vector<boost::asio::mutable_buffer> seq;
  FC_ASSERT(write_ind.first < buffers.size());
  seq.push_back(boost::asio::buffer(&buffers[write_ind.first]->at(write_ind.second),
                                            buffer_len - write_ind.second));
  for (std::size_t i = write_ind.first + 1; i < buffers.size(); i++) {
    seq.push_back(boost::asio::buffer(&buffers[i]->at(0), buffer_len));
  }
  return seq;
}
```
</br>

# 三、网络的连接
</br>
处理完成监听和接收，来看一下主动连接：
</br>

``` c++
void net_plugin_impl::start_monitors() {
   connector_check.reset(new boost::asio::steady_timer( app().get_io_service()));
   transaction_check.reset(new boost::asio::steady_timer( app().get_io_service()));
   start_conn_timer();//调用两个函数
   start_txn_timer();
}
//调用的start_conn_timer
void net_plugin_impl::start_conn_timer( ) {
   connector_check->expires_from_now( connector_period);// 设置定时器
   connector_check->async_wait( [&](boost::system::error_code ec) {
         if( !ec) {
            connection_monitor( );//调用连接监控
         }
         else {
            elog( "Error from connection check monitor: ${m}",( "m", ec.message()));
            start_conn_timer( );
         }
      });
}
void net_plugin_impl::connection_monitor( ) {
   start_conn_timer();//循环调用
   vector <connection_ptr> discards;
   num_clients = 0;
   for( auto &c : connections ) {
      if( !c->socket->is_open() && !c->connecting) {
         if( c->peer_addr.length() > 0) {
            connect(c);//连接指定的点。
         }
         else {
            discards.push_back( c);
         }
      } else {
         if( c->peer_addr.empty()) {
            num_clients++;
         }
      }
   }
   //处理断开的连接
   if( discards.size( ) ) {
      for( auto &c : discards) {
         connections.erase( c );
         c.reset();
      }
   }
}
//交易的定时器监视
void net_plugin_impl::start_txn_timer() {
   transaction_check->expires_from_now( txn_exp_period);
   transaction_check->async_wait( [&](boost::system::error_code ec) {
         if( !ec) {
            expire_txns( );//处理到期交易的情况
         }
         else {
            elog( "Error from transaction check monitor: ${m}",( "m", ec.message()));
            start_txn_timer( );
         }
      });
}
void net_plugin_impl::expire_txns() {
   start_txn_timer( );
   auto &old = local_txns.get<by_expiry>();
   auto ex_up = old.upper_bound( time_point::now());
   auto ex_lo = old.lower_bound( fc::time_point_sec( 0));
   old.erase( ex_lo, ex_up);

   auto &stale = local_txns.get<by_block_num>();
   chain_controller &cc = chain_plug->chain();
   uint32_t bn = cc.last_irreversible_block_num();
   auto bn_up = stale.upper_bound(bn);
   auto bn_lo = stale.lower_bound(1);
   stale.erase( bn_lo, bn_up);
}
```
</br>
最后看一看连接的代码：
</br>

``` c++

/**
 *  Used to trigger a new connection from RPC API
 */
string net_plugin::connect( const string& host ) {
   if( my->find_connection( host ) )
      return "already connected";

   connection_ptr c = std::make_shared<connection>(host);
   fc_dlog(my->logger,"adding new connection to the list");
   my->connections.insert( c );
   fc_dlog(my->logger,"calling active connector");
   my->connect( c );
   return "added connection";
}
//两个连接的重载，其实都很简单，第个Connect负责解析，第二个Connect负责真正连接
void net_plugin_impl::connect( connection_ptr c ) {
   if( c->no_retry != go_away_reason::no_reason) {
      fc_dlog( logger, "Skipping connect due to go_away reason ${r}",("r", reason_str( c->no_retry )));
      return;
   }

   auto colon = c->peer_addr.find(':');

   if (colon == std::string::npos || colon == 0) {
      elog ("Invalid peer address. must be \"host:port\": ${p}", ("p",c->peer_addr));
      return;
   }

   auto host = c->peer_addr.substr( 0, colon );
   auto port = c->peer_addr.substr( colon + 1);
   idump((host)(port));
   tcp::resolver::query query( tcp::v4(), host.c_str(), port.c_str() );
   // Note: need to add support for IPv6 too

   resolver->async_resolve( query,
                            [c, this]( const boost::system::error_code& err,
                                       tcp::resolver::iterator endpoint_itr ){
                               if( !err ) {
                                  connect( c, endpoint_itr );
                               } else {
                                  elog( "Unable to resolve ${peer_addr}: ${error}",
                                        (  "peer_addr", c->peer_name() )("error", err.message() ) );
                               }
                            });
}

void net_plugin_impl::connect( connection_ptr c, tcp::resolver::iterator endpoint_itr ) {
   if( c->no_retry != go_away_reason::no_reason) {
      string rsn = reason_str(c->no_retry);
      return;
   }
   auto current_endpoint = \*endpoint_itr;
   ++endpoint_itr;
   c->connecting = true;
   c->socket->async_connect( current_endpoint, [c, endpoint_itr, this] ( const boost::system::error_code& err ) {
         if( !err ) {
            start_session( c );//读取数据
            c->send_handshake ();//发送握手
         } else {
            if( endpoint_itr != tcp::resolver::iterator() ) {
               c->close();
               connect( c, endpoint_itr );
            }
            else {
               elog( "connection failed to ${peer}: ${error}",
                     ( "peer", c->peer_name())("error",err.message()));
               c->connecting = false;
               my_impl->close(c);
            }
         }
      } );
}
```
</br>

# 四、网络的数据同步
</br>
在前面看了start_read_message，对内部没有怎么做细节的分析，网络也启动了，节点也发现了，那么P2P的职责开始实现了，首先就是同步数据,和比特币类似，也有一个中心的消息处理系统，名字都有点像。
</br>

``` c++
bool connection::process_next_message(net_plugin_impl& impl, uint32_t message_length) {
   try {
      // If it is a signed_block, then save the raw message for the cache
      // This must be done before we unpack the message.
      // This code is copied from fc::io::unpack(..., unsigned_int)
      auto index = pending_message_buffer.read_index();
      uint64_t which = 0; char b = 0; uint8_t by = 0;
      do {
         pending_message_buffer.peek(&b, 1, index);
         which |= uint32_t(uint8_t(b) & 0x7f) << by;
         by += 7;
      } while( uint8_t(b) & 0x80 );

      if (which == uint64_t(net_message::tag<signed_block>::value)) {
         blk_buffer.resize(message_length);
         auto index = pending_message_buffer.read_index();
         pending_message_buffer.peek(blk_buffer.data(), message_length, index);
      }
      auto ds = pending_message_buffer.create_datastream();
      net_message msg;
      fc::raw::unpack(ds, msg);
      msgHandler m(impl, shared_from_this() );//impl是net_plugin_impl
      msg.visit(m);//注意这里最终是调用一个仿函数，static_variant.hpp中
   } catch(  const fc::exception& e ) {
      edump((e.to_detail_string() ));
      impl.close( shared_from_this() );
      return false;
   }
   return true;
}

//仿函数实现是通过重载了小括号
struct msgHandler : public fc::visitor<void> {
   net_plugin_impl &impl;
   connection_ptr c;
   msgHandler( net_plugin_impl &imp, connection_ptr conn) : impl(imp), c(conn) {}

   template <typename T>
   void operator()(const T &msg) const
   {
      impl.handle_message( c, msg); //这里会调用net_plugin_impl中的handle_message
   }
};
```
</br>
下面开始调用分发函数：

</br>

``` c++
void net_plugin_impl::handle_message( connection_ptr c, const handshake_message &msg) {
   fc_dlog( logger, "got a handshake_message from ${p} ${h}", ("p",c->peer_addr)("h",msg.p2p_address));
   if (!is_valid(msg)) {
      elog( "Invalid handshake message received from ${p} ${h}", ("p",c->peer_addr)("h",msg.p2p_address));
      c->enqueue( go_away_message( fatal_other ));
      return;
   }
   chain_controller& cc = chain_plug->chain();
   uint32_t lib_num = cc.last_irreversible_block_num( );
   uint32_t peer_lib = msg.last_irreversible_block_num;
   if( c->connecting ) {
      c->connecting = false;
   }
   if (msg.generation == 1) {
      if( msg.node_id == node_id) {
         elog( "Self connection detected. Closing connection");
         c->enqueue( go_away_message( self ) );
         return;
      }

      if( c->peer_addr.empty() || c->last_handshake_recv.node_id == fc::sha256()) {
         fc_dlog(logger, "checking for duplicate" );
         for(const auto &check : connections) {
            if(check == c)
               continue;
            if(check->connected() && check->peer_name() == msg.p2p_address) {
               // It's possible that both peers could arrive here at relatively the same time, so
               // we need to avoid the case where they would both tell a different connection to go away.
               // Using the sum of the initial handshake times of the two connections, we will
               // arbitrarily (but consistently between the two peers) keep one of them.
               if (msg.time + c->last_handshake_sent.time <= check->last_handshake_sent.time + check->last_handshake_recv.time)
                  continue;

               fc_dlog( logger, "sending go_away duplicate to ${ep}", ("ep",msg.p2p_address) );
               go_away_message gam(duplicate);
               gam.node_id = node_id;
               c->enqueue(gam);
               c->no_retry = duplicate;
               return;
            }
         }
      }
      else {
         fc_dlog(logger, "skipping duplicate check, addr == ${pa}, id = ${ni}",("pa",c->peer_addr)("ni",c->last_handshake_recv.node_id));
      }

      if( msg.chain_id != chain_id) {
         elog( "Peer on a different chain. Closing connection");
         c->enqueue( go_away_message(go_away_reason::wrong_chain) );
         return;
      }
      if( msg.network_version != network_version) {
         if (network_version_match) {
            elog("Peer network version does not match expected ${nv} but got ${mnv}",
                 ("nv", network_version)("mnv", msg.network_version));
            c->enqueue(go_away_message(wrong_version));
            return;
         } else {
            wlog("Peer network version does not match expected ${nv} but got ${mnv}",
                 ("nv", network_version)("mnv", msg.network_version));
         }
      }

      if(  c->node_id != msg.node_id) {
         c->node_id = msg.node_id;
      }

      if(!authenticate_peer(msg)) {
         elog("Peer not authenticated.  Closing connection.");
         c->enqueue(go_away_message(authentication));
         return;
      }

      bool on_fork = false;
      fc_dlog(logger, "lib_num = ${ln} peer_lib = ${pl}",("ln",lib_num)("pl",peer_lib));

      if( peer_lib <= lib_num && peer_lib > 0) {
         try {
            block_id_type peer_lib_id =  cc.get_block_id_for_num( peer_lib);
            on_fork =( msg.last_irreversible_block_id != peer_lib_id);
         }
         catch( const unknown_block_exception &ex) {
            wlog( "peer last irreversible block ${pl} is unknown", ("pl", peer_lib));
            on_fork = true;
         }
         catch( ...) {
            wlog( "caught an exception getting block id for ${pl}",("pl",peer_lib));
            on_fork = true;
         }
         if( on_fork) {
            elog( "Peer chain is forked");
            c->enqueue( go_away_message( forked ));
            return;
         }
      }

      if (c->sent_handshake_count == 0) {
         c->send_handshake();
      }
   }

   c->last_handshake_recv = msg;
   sync_master->recv_handshake(c,msg);//这里开始同步
}
void sync_manager::recv_handshake (connection_ptr c, const handshake_message &msg) {
   chain_controller& cc = chain_plug->chain();
......
   //--------------------------------
   // sync need checkz; (lib == last irreversible block)
   //
   // 0. my head block id == peer head id means we are all caugnt up block wise
   // 1. my head block num < peer lib - start sync locally
   // 2. my lib > peer head num - send an last_irr_catch_up notice if not the first generation
   //
   // 3  my head block num <= peer head block num - update sync state and send a catchup request
   // 4  my head block num > peer block num ssend a notice catchup if this is not the first generation
   //
   //-----------------------------

   uint32_t head = cc.head_block_num( );
   block_id_type head_id = cc.head_block_id();
   if (head_id == msg.head_id) {
      fc_dlog(logger, "sync check state 0");
      // notify peer of our pending transactions
      notice_message note;
      note.known_blocks.mode = none;
      note.known_trx.mode = catch_up;
      note.known_trx.pending = my_impl->local_txns.size();
      c->enqueue( note );
      return;
   }
   if (head < peer_lib) {
      fc_dlog(logger, "sync check state 1");
      start_sync( c, peer_lib);//同步
      return;
   }
......
}



```
</br>
再深入的细节就不再分析了，就是基本的数据交互通信。
