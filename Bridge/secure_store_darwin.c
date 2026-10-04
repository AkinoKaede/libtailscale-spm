#include "spm_bridge.h"
#include <Security/Security.h>
#include <CoreFoundation/CoreFoundation.h>
#include <TargetConditionals.h>
#include <stdlib.h>
#include <string.h>

static CFMutableDictionaryRef query(const char *scope, const char *key) {
    CFMutableDictionaryRef q = CFDictionaryCreateMutable(NULL, 0,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFStringRef service = CFStringCreateWithCString(NULL, scope, kCFStringEncodingUTF8);
    CFStringRef account = CFStringCreateWithCString(NULL, key, kCFStringEncodingUTF8);
    CFDictionarySetValue(q, kSecClass, kSecClassGenericPassword);
    CFDictionarySetValue(q, kSecAttrService, service);
    CFDictionarySetValue(q, kSecAttrAccount, account);
    CFDictionarySetValue(q, kSecAttrSynchronizable, kCFBooleanFalse);
    CFRelease(service);
    CFRelease(account);
    return q;
}

int lt_store_read(const char *scope, const char *key, void **data, int *length) {
    *data = NULL;
    *length = 0;
    CFMutableDictionaryRef q = query(scope, key);
    CFDictionarySetValue(q, kSecReturnData, kCFBooleanTrue);
    CFDictionarySetValue(q, kSecMatchLimit, kSecMatchLimitOne);
    CFTypeRef result = NULL;
    OSStatus status = SecItemCopyMatching(q, &result);
    CFRelease(q);
    if (status != errSecSuccess) return (int)status;
    *length = (int)CFDataGetLength((CFDataRef)result);
    *data = malloc(*length ? (size_t)*length : 1);
    if (!*data) { CFRelease(result); return -1; }
    memcpy(*data, CFDataGetBytePtr((CFDataRef)result), (size_t)*length);
    CFRelease(result);
    return 0;
}

int lt_store_write(const char *scope, const char *key, const void *data, int length) {
    CFMutableDictionaryRef q = query(scope, key);
    CFDataRef value = CFDataCreate(NULL, data, length);
    CFMutableDictionaryRef attributes = CFDictionaryCreateMutable(NULL, 0,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    CFDictionarySetValue(attributes, kSecValueData, value);
    CFDictionarySetValue(attributes, kSecAttrAccessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly);
    OSStatus status = SecItemUpdate(q, attributes);
    if (status == errSecItemNotFound) {
        CFDictionarySetValue(q, kSecValueData, value);
        CFDictionarySetValue(q, kSecAttrAccessible, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly);
        status = SecItemAdd(q, NULL);
    }
    CFRelease(value);
    CFRelease(attributes);
    CFRelease(q);
    return (int)status;
}

int lt_store_delete_scope(const char *scope) {
    CFMutableDictionaryRef q = query(scope, "");
    CFDictionaryRemoveValue(q, kSecAttrAccount);
#if TARGET_OS_OSX
    // The macOS file-based keychain otherwise deletes only the first match.
    CFDictionarySetValue(q, kSecMatchLimit, kSecMatchLimitAll);
#endif
    OSStatus status = SecItemDelete(q);
    CFRelease(q);
    return status == errSecItemNotFound ? 0 : (int)status;
}
