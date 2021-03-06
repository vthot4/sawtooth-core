/*
 * Copyright 2018-2020 Cargill Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * ------------------------------------------------------------------------------
 */

#[macro_use]
extern crate cfg_if;
extern crate crypto;
extern crate hex;
extern crate protobuf;

cfg_if! {
    if #[cfg(target_arch = "wasm32")] {
        #[macro_use]
        extern crate sabre_sdk;
    } else {
        #[macro_use]
        extern crate log;
        extern crate log4rs;
        extern crate rustc_serialize;
        extern crate sawtooth_sdk;
    }
}

pub mod addressing;
pub mod handler;
pub mod payload;
pub mod protos;
pub mod state;
