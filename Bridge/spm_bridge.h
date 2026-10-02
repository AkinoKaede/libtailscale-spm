#ifndef LIBTAILSCALE_SPM_BRIDGE_H
#define LIBTAILSCALE_SPM_BRIDGE_H
#include <stddef.h>
#include "tailscale.h"
int lt_store_delete_scope(const char *scope);
int lt_store_read(const char *scope, const char *key, void **data, int *length);
int lt_store_write(const char *scope, const char *key, const void *data, int length);
int LtConfigureStore(int node, char *scope);
unsigned long long LtNewOperation(void);
void LtCancelOperation(unsigned long long operation);
void LtReleaseOperation(unsigned long long operation);
int LtDial(int node, char *address, unsigned long long operation, int seconds, int *fd, char **error);
int LtRequest(int node, char *method, char *path, char *body,
              unsigned long long operation, int seconds, char **response, char **error);
char *LtVersion(void);
#endif
