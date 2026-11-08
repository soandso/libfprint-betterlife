/*
 * Betterlife (BLESTECH) match-on-chip USB fingerprint module, 347d:0302
 *
 * Protocol reverse-engineered from the vendor Windows WBDI driver for
 * interoperability; see docs/PROTOCOL.md in the libfprint-betterlife project.
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 */

#pragma once

#include "fpi-device.h"
#include "fpi-ssm.h"

#define BTL_EP_OUT (0x02 | FPI_USB_ENDPOINT_OUT)
#define BTL_EP_IN (0x01 | FPI_USB_ENDPOINT_IN)

#define BTL_SYNC 0xAA
#define BTL_MAGIC 0x4C
#define BTL_IV_LEN 16
#define BTL_KEY_LEN 16
#define BTL_HDR_LEN (1 + 4 + BTL_IV_LEN)               /* AA, L, IV */
#define BTL_BODY_HDR_LEN 10                            /* 4C cmd p1 00 p2 p3 len32 */
#define BTL_MAX_FRAME 0x4000

#define BTL_IDENTITY_LEN 32
#define BTL_TAG_LEN 16

#define BTL_CMD_FW_VERSION 0xA0
#define BTL_CMD_SCHEME 0xA1
#define BTL_CMD_KEY_EXCHANGE 0xA2
#define BTL_CMD_ENROLL 0xB0
#define BTL_CMD_IDENTIFY 0xB1
#define BTL_CMD_REMOVE 0xB2
#define BTL_CMD_COUNT 0xB3

#define BTL_ENROLL_START 0
#define BTL_ENROLL_TOUCH 1
#define BTL_ENROLL_FINISH 2
#define BTL_ENROLL_CANCEL 3
#define BTL_REMOVE_IDENTITY 1       /* data: 32-byte identity; all-zero = remove ALL (never sent) */
#define BTL_IDENTIFY_START 0
#define BTL_IDENTIFY_CANCEL 1

/* Status byte (data[0]) of enroll/identify results */
#define BTL_ST_OK 0x00
#define BTL_ST_NO_FINGER 0x10
#define BTL_ST_LIFT_TOO_FAST 0x11
#define BTL_ST_DUPLICATE 0x12
#define BTL_ST_SAVE_FAILED 0x13
#define BTL_ST_OVERLAP 0x14
#define BTL_ST_NO_MATCH 0x21
#define BTL_ST_FINGER_AWAY 0x30
#define BTL_ST_ALGO_FAILED 0x31
#define BTL_ST_NOT_LIVE 0x32
#define BTL_ST_TOO_WET 0x33
#define BTL_ST_TOO_DRY 0x34
#define BTL_ST_AREA_SMALL 0x35
#define BTL_ST_POOR_QUALITY 0x36
#define BTL_ST_FLASH_FAILED 0x41

#define BTL_DEFAULT_ENROLL_STAGES 7

G_DECLARE_FINAL_TYPE (FpiDeviceBetterlife, fpi_device_betterlife, FPI,
                      DEVICE_BETTERLIFE, FpDevice)
